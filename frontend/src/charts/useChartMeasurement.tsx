import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { IChartApi, ISeriesApi, Logical } from "lightweight-charts";
import type { Bar } from "../types";

type Selection = [number, number];
interface View {
  width: number;
  height: number;
  selection: Selection | null;
  points: [number, number, number, number] | null;
}

export function useChartMeasurement(bars: Bar[]) {
  const api = useRef<{ chart: IChartApi; candle: ISeriesApi<"Candlestick"> } | null>(null);
  const selection = useRef<Selection | null>(null);
  const drag = useRef<{ pointer: number; endpoint: 0 | 1; previous: Selection | null } | null>(null);
  const surface = useRef<HTMLDivElement>(null);
  const frame = useRef(0);
  const [enabled, setEnabled] = useState(false);
  const [shift, setShift] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [view, setView] = useState<View>({ width: 0, height: 0, selection: null, points: null });

  const redraw = useCallback(() => {
    if (!api.current) return;
    const { chart, candle } = api.current;
    const { width, height } = chart.paneSize(0);
    const pair = selection.current;
    let points: View["points"] = null;
    if (pair && bars[pair[0]] && bars[pair[1]]) {
      const x1 = chart.timeScale().logicalToCoordinate(pair[0] as Logical);
      const x2 = chart.timeScale().logicalToCoordinate(pair[1] as Logical);
      const y1 = candle.priceToCoordinate(bars[pair[0]].close);
      const y2 = candle.priceToCoordinate(bars[pair[1]].close);
      if (x1 !== null && x2 !== null && y1 !== null && y2 !== null) points = [x1, y1, x2, y2];
    }
    setView((old) => {
      const next = { width, height, selection: pair, points };
      return JSON.stringify(old) === JSON.stringify(next) ? old : next;
    });
  }, [bars]);

  const endDrag = useCallback(() => {
    const pointer = drag.current?.pointer;
    drag.current = null;
    if (pointer !== undefined && surface.current?.hasPointerCapture(pointer)) {
      surface.current.releasePointerCapture(pointer);
    }
    setDragging(false);
  }, []);

  const clear = useCallback(() => {
    endDrag();
    selection.current = null;
    setEnabled(false);
    redraw();
  }, [endDrag, redraw]);

  const attach = useCallback((chart: IChartApi, candle: ISeriesApi<"Candlestick">) => {
    api.current = { chart, candle };
    return () => {
      endDrag();
      api.current = null;
    };
  }, [endDrag]);

  useEffect(() => { clear(); }, [bars, clear]);

  useEffect(() => {
    const isEditing = (target: EventTarget | null) => target instanceof HTMLElement &&
      (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
    const down = (event: KeyboardEvent) => {
      if (isEditing(event.target)) return;
      if (event.key === "Shift") setShift(true);
      if (event.key === "Escape") clear();
    };
    const up = (event: KeyboardEvent) => { if (event.key === "Shift") setShift(false); };
    const blur = () => {
      setShift(false);
      if (drag.current) {
        selection.current = drag.current.previous;
        endDrag();
        redraw();
      }
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    window.addEventListener("blur", blur);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
      window.removeEventListener("blur", blur);
    };
  }, [clear, endDrag, redraw]);

  // The chart has no price-scale change subscription. Keep retained measurements
  // aligned during vertical scaling as well as horizontal pan/zoom.
  const hasSelection = view.selection !== null;
  useEffect(() => {
    if (!hasSelection) return;
    const tick = () => { redraw(); frame.current = requestAnimationFrame(tick); };
    frame.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame.current);
  }, [hasSelection, redraw]);

  const indexAt = (event: ReactPointerEvent) => {
    if (!api.current || !surface.current || !bars.length) return null;
    const rect = surface.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
    const logical = api.current.chart.timeScale().coordinateToLogical(x);
    return logical === null ? null : Math.max(0, Math.min(bars.length - 1, Math.round(logical)));
  };
  const start = (event: ReactPointerEvent, endpoint?: 0 | 1) => {
    if (event.button !== 0 || drag.current || (!enabled && !shift && endpoint === undefined)) return;
    const index = indexAt(event);
    if (index === null) return;
    event.preventDefault();
    event.stopPropagation();
    drag.current = { pointer: event.pointerId, endpoint: endpoint ?? 1, previous: selection.current };
    if (endpoint === undefined) selection.current = [index, index];
    surface.current?.setPointerCapture(event.pointerId);
    setDragging(true);
    redraw();
  };
  const move = (event: ReactPointerEvent) => {
    if (drag.current?.pointer !== event.pointerId || !selection.current) return;
    const index = indexAt(event);
    if (index === null) return;
    const next: Selection = [...selection.current];
    next[drag.current.endpoint] = index;
    selection.current = next;
    redraw();
  };
  const finish = (event: ReactPointerEvent, cancel = false) => {
    if (drag.current?.pointer !== event.pointerId) return;
    if (cancel) selection.current = drag.current.previous;
    else move(event);
    endDrag();
    redraw();
  };

  const pair = view.selection;
  const first = pair ? bars[Math.min(...pair)] : null;
  const last = pair ? bars[Math.max(...pair)] : null;
  const difference = first && last ? last.close - first.close : 0;
  const change = first && last && first.close !== 0 ? difference / first.close * 100 : null;
  const signed = (value: number, decimals: number) => `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(decimals)}`;
  const points = view.points;
  const visible = points && Math.max(points[0], points[2]) >= 0 && Math.min(points[0], points[2]) <= view.width;
  const left = points ? Math.min(points[0], points[2]) : 0;
  const top = points ? Math.min(points[1], points[3]) : 0;
  const cardWidth = Math.min(270, view.width);

  return {
    attach,
    redraw,
    button: <button className={`text-button measure-toggle ${enabled ? "active" : ""}`}
      aria-pressed={enabled} title="拖动测量两根 K 线的涨跌幅，也可按住 Shift 拖动"
      onClick={() => setEnabled((value) => !value)}>↔ 测量</button>,
    overlay: <div ref={surface} className={`chart-measurement ${enabled || shift || dragging ? "measuring" : ""}`}
      style={{ width: view.width, height: view.height }}
      onPointerDown={(event) => start(event)} onPointerMove={move}
      onPointerUp={(event) => finish(event)} onPointerCancel={(event) => finish(event, true)}
      onLostPointerCapture={(event) => { if (drag.current) finish(event, true); }}>
      {(enabled || shift) && !pair && <div className="measurement-hint">拖动选择两根 K 线 · 收盘价测量 · Esc 退出</div>}
      {visible && points && first && last && pair && <>
        <svg className="measurement-drawing" width={view.width} height={view.height}
          style={{ color: difference > 0 ? "#ca555e" : difference < 0 ? "#168b77" : "#68768a" }}>
          <rect x={left} y={top} width={Math.abs(points[2] - points[0])} height={Math.max(1, Math.abs(points[3] - points[1]))}
            fill="currentColor" fillOpacity="0.07" stroke="currentColor" strokeDasharray="4 4" />
          {[0, 2].map((offset) => <line key={offset} x1={points[offset]} x2={points[offset]} y1={0} y2={view.height}
            stroke="currentColor" strokeOpacity="0.4" strokeDasharray="4 4" />)}
          <line x1={points[0]} y1={points[1]} x2={points[2]} y2={points[3]} stroke="currentColor" strokeWidth="1.5" />
        </svg>
        {([0, 1] as const).map((endpoint) => <button key={endpoint} className="measurement-endpoint"
          aria-label={`调整测量端点 ${endpoint + 1}`} title="拖动调整；方向键移动一根 K 线"
          style={{ left: points[endpoint * 2] - 8, top: points[endpoint * 2 + 1] - 8 }}
          onPointerDown={(event) => start(event, endpoint)}
          onKeyDown={(event) => {
            if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
            event.preventDefault();
            const next: Selection = [...pair];
            next[endpoint] = Math.max(0, Math.min(bars.length - 1, next[endpoint] + (event.key === "ArrowLeft" ? -1 : 1)));
            selection.current = next;
            redraw();
          }} />)}
        <aside className="measurement-result" aria-label="区间测量结果"
          style={{ width: cardWidth, left: Math.max(0, Math.min(view.width - cardWidth, left)),
            top: Math.max(0, Math.min(view.height - 104, top >= 112 ? top - 104 : Math.max(points[1], points[3]) + 14)) }}
          onPointerDown={(event) => event.stopPropagation()}>
          <button className="measurement-close" aria-label="清除测量" onClick={clear}>×</button>
          <strong style={{ color: difference > 0 ? "#ca555e" : difference < 0 ? "#168b77" : "#68768a" }}>
            {change === null ? "—" : `${signed(change, 2)}%`} <small>{signed(difference, 3)} 元</small>
          </strong>
          <span>¥{first.close.toFixed(3)} → ¥{last.close.toFixed(3)} · 收盘价</span>
          <span>{first.date} → {last.date}</span>
          <span>间隔 {Math.abs(pair[1] - pair[0])} 根 K 线</span>
        </aside>
      </>}
    </div>,
  };
}
