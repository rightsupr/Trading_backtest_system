import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
} from "lightweight-charts";
import type {
  IChartApi,
  Time,
  Logical,
  SeriesMarker,
} from "lightweight-charts";
import type { Bar, Fill, Run, Trade } from "../types";
import { percent } from "../services/api";

interface Props {
  bars: Bar[];
  run: Run | null;
  selected: Trade | null;
  onSelect: (trade: Trade) => void;
  onFill: (fill: Fill) => void;
}
interface Region {
  id: string;
  left: number;
  width: number;
  text: string;
  positive: boolean;
  selected: boolean;
}

export default function PriceChart({
  bars,
  run,
  selected,
  onSelect,
  onFill,
}: Props) {
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const callbacks = useRef({ onSelect, onFill });
  callbacks.current = { onSelect, onFill };
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const redraw = useRef<() => void>(() => {});
  const [hover, setHover] = useState<Bar | null>(null);
  const [regions, setRegions] = useState<Region[]>([]);
  const [paneHeight, setPaneHeight] = useState(350);
  const [volumeHeight, setVolumeHeight] = useState(100);
  const [plotWidth, setPlotWidth] = useState(0);
  const [clickedFill, setClickedFill] = useState<Fill | null>(null);

  useEffect(() => {
    if (!host.current || bars.length === 0) return;
    setClickedFill(null);
    const chart = createChart(host.current, {
      autoSize: true,
      height: 610,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#8791a2",
        fontSize: 11,
        fontFamily: "ui-monospace, SFMono-Regular, monospace",
        panes: { separatorColor: "#e9edf2", enableResize: false },
      },
      grid: {
        vertLines: { color: "#f4f6f8" },
        horzLines: { color: "#f0f3f6" },
      },
      rightPriceScale: { borderColor: "#edf0f4", minimumWidth: 72 },
      timeScale: {
        borderColor: "#edf0f4",
        rightOffset: 5,
        barSpacing: 7,
        timeVisible: false,
      },
      crosshair: {
        mode: 0,
        vertLine: { color: "#929cac", labelBackgroundColor: "#344455" },
        horzLine: { color: "#929cac", labelBackgroundColor: "#344455" },
      },
      localization: { locale: "zh-CN" },
    });
    chartRef.current = chart;
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: "#d75d62",
      downColor: "#15947c",
      borderVisible: false,
      wickUpColor: "#d75d62",
      wickDownColor: "#15947c",
      priceLineVisible: false,
    });
    candle.setData(
      bars.map((b) => ({
        time: b.date,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );
    const fast = chart.addSeries(LineSeries, {
      color: "#d6a148",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const slow = chart.addSeries(LineSeries, {
      color: "#718bc3",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const isMA = run?.request.strategy_name === "ma_cross";
    fast.setData(
      bars.map((b) => {
        const v = isMA ? b.strategy_fast : b.sma_5;
        return v == null ? { time: b.date } : { time: b.date, value: v };
      }),
    );
    slow.setData(
      bars.map((b) => {
        const v = isMA ? b.strategy_slow : b.sma_20;
        return v == null ? { time: b.date } : { time: b.date, value: v };
      }),
    );
    const volume = chart.addSeries(
      HistogramSeries,
      {
        priceFormat: { type: "volume" },
        priceLineVisible: false,
        lastValueVisible: false,
      },
      1,
    );
    volume.setData(
      bars.map((b) => ({
        time: b.date,
        value: b.volume,
        color: b.close >= b.open ? "#d75d6277" : "#15947c77",
      })),
    );
    const hist = chart.addSeries(
      HistogramSeries,
      { priceLineVisible: false, lastValueVisible: false },
      2,
    );
    hist.setData(
      bars.map((b) =>
        b.macd_hist == null
          ? { time: b.date }
          : {
              time: b.date,
              value: b.macd_hist,
              color: b.macd_hist >= 0 ? "#d75d6299" : "#15947c99",
            },
      ),
    );
    for (const [key, color] of [
      ["macd_dif", "#d6a148"],
      ["macd_dea", "#718bc3"],
    ] as const) {
      const line = chart.addSeries(
        LineSeries,
        {
          color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        },
        2,
      );
      line.setData(
        bars.map((b) =>
          b[key] == null ? { time: b.date } : { time: b.date, value: b[key] },
        ),
      );
    }
    chart.panes()[0].setStretchFactor(350);
    chart.panes()[1].setStretchFactor(100);
    chart.panes()[2].setStretchFactor(132);
    const fills = run?.fills ?? [];
    const markers: SeriesMarker<Time>[] = fills.map((f, i) => ({
      id: `fill-${i}`,
      time: f.date,
      position: f.side === "BUY" ? "belowBar" : "aboveBar",
      shape: f.side === "BUY" ? "arrowUp" : "arrowDown",
      color: f.side === "BUY" ? "#cb5159" : "#138675",
      text: f.side,
      size: 1,
    }));
    const markerPlugin = createSeriesMarkers(candle, markers);
    const byDate = new Map(bars.map((b) => [b.date, b]));
    chart.subscribeCrosshairMove((event) => {
      const time = event.time;
      const date =
        typeof time === "string"
          ? time
          : time && typeof time === "object"
            ? `${time.year}-${String(time.month).padStart(2, "0")}-${String(time.day).padStart(2, "0")}`
            : "";
      setHover(byDate.get(date) ?? null);
    });
    chart.subscribeClick((event) => {
      if (
        typeof event.hoveredObjectId !== "string" ||
        !event.hoveredObjectId.startsWith("fill-")
      )
        return;
      const fill = fills[Number(event.hoveredObjectId.slice(5))];
      if (!fill) return;
      setClickedFill(fill);
      const trade = run?.trades.find((t) => t.trade_id === fill.trade_id);
      if (trade) callbacks.current.onSelect(trade);
      callbacks.current.onFill(fill);
    });
    const indices = new Map(bars.map((b, i) => [b.date, i]));
    let raf = 0;
    const draw = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const width = chart.paneSize(0).width;
        setPlotWidth(width);
        setPaneHeight(chart.panes()[0].getHeight());
        setVolumeHeight(chart.panes()[1].getHeight());
        const intervals = (run?.trades ?? []).map((t) => ({
          id: t.trade_id,
          start: t.entry_date,
          end: t.exit_date,
          text: percent(t.net_return),
          positive: t.net_return >= 0,
        }));
        if (run?.open_position)
          intervals.push({
            id: run.open_position.trade_id,
            start: run.open_position.entry_date,
            end: run.open_position.last_date,
            text: "持仓中",
            positive: run.open_position.unrealized_profit >= 0,
          });
        setRegions(
          intervals.flatMap((t) => {
            const a = indices.get(t.start),
              b = indices.get(t.end);
            if (a === undefined || b === undefined) return [];
            // v5 coordinates accept integer indices; pad using the measured bar width.
            const startX = chart.timeScale().logicalToCoordinate(a as Logical);
            const endX = chart.timeScale().logicalToCoordinate(b as Logical);
            const adjacentX = chart
              .timeScale()
              .logicalToCoordinate((a + 1) as Logical);
            if (startX === null || endX === null || adjacentX === null)
              return [];
            const halfBar = Math.abs(adjacentX - startX) * 0.45;
            const left = startX - halfBar,
              right = endX + halfBar;
            if (right < 0 || left > width) return [];
            return [
              {
                id: t.id,
                left: Math.max(0, left),
                width: Math.min(width, right) - Math.max(0, left),
                text: t.text,
                positive: t.positive,
                selected: selectedRef.current?.trade_id === t.id,
              },
            ];
          }),
        );
      });
    };
    redraw.current = draw;
    chart.timeScale().subscribeVisibleLogicalRangeChange(draw);
    const observer = new ResizeObserver(draw);
    observer.observe(host.current);
    chart.timeScale().fitContent();
    draw();
    return () => {
      observer.disconnect();
      cancelAnimationFrame(raf);
      markerPlugin.detach();
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, run]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !selected) return;
    const start = bars.findIndex((b) => b.date === selected.entry_date);
    const end = bars.findIndex((b) => b.date === selected.exit_date);
    if (start >= 0 && end >= 0) {
      setHover(bars[end]);
      chart
        .timeScale()
        .setVisibleLogicalRange({ from: start - 10, to: end + 10 });
    }
    redraw.current();
  }, [selected, bars]);

  const current = hover ?? bars.at(-1);
  if (!bars.length)
    return (
      <div className="chart-empty">
        <span className="empty-candles">▂ ▆ ▄ █ ▅ ▇ ▃</span>
        <h3>从一只股票，开始一次研究</h3>
        <p>选择日期并下载历史行情，K 线与技术指标将在这里呈现。</p>
        <span>本地存储 · 次日开盘撮合 · 逐笔交易复盘</span>
      </div>
    );
  return (
    <div className="price-chart">
      <div className="chart-legend">
        <strong>{current?.date}</strong>
        {current && (
          <>
            <span>
              开 <b>{current.open.toFixed(2)}</b>
            </span>
            <span>
              高 <b>{current.high.toFixed(2)}</b>
            </span>
            <span>
              低 <b>{current.low.toFixed(2)}</b>
            </span>
            <span>
              收 <b>{current.close.toFixed(2)}</b>
            </span>
          </>
        )}
        <span className="legend-fast">
          MA{" "}
          {run?.request.strategy_name === "ma_cross"
            ? run.request.parameters.fast_ma
            : 5}
        </span>
        <span className="legend-slow">
          MA{" "}
          {run?.request.strategy_name === "ma_cross"
            ? run.request.parameters.slow_ma
            : 20}
        </span>
        <button
          className="text-button"
          onClick={() => chartRef.current?.timeScale().fitContent()}
        >
          显示全部
        </button>
      </div>
      <div className="chart-canvas" ref={host} />
      <div
        className="regions"
        style={{ height: paneHeight, width: plotWidth }}
        aria-hidden="true"
      >
        {regions.map((region) => (
          <div
            key={region.id}
            className={`holding-region ${region.positive ? "profit-region" : "loss-region"} ${region.selected ? "active" : ""}`}
            style={{ left: region.left, width: region.width }}
          >
            {region.width > 40 && <span>{region.text}</span>}
          </div>
        ))}
      </div>
      <span
        className="pane-label volume-label"
        style={{ top: paneHeight + 43 }}
      >
        成交量 · 股
      </span>
      <span
        className="pane-label macd-label"
        style={{ top: paneHeight + volumeHeight + 44 }}
      >
        MACD <i>DIF</i> <em>DEA</em> ·{" "}
        {run?.request.strategy_name === "macd"
          ? Object.values(run.request.parameters).join(" / ")
          : "12 / 26 / 9"}
      </span>
      {clickedFill && (
        <aside className="marker-tooltip">
          <button
            aria-label="关闭成交详情"
            onClick={() => setClickedFill(null)}
          >
            ×
          </button>
          <strong>
            {clickedFill.side} · {clickedFill.date} · ¥
            {clickedFill.price.toFixed(3)}
          </strong>
          <span>
            {run?.request.strategy_name} · {clickedFill.shares.toLocaleString()}{" "}
            股
          </span>
          <p>{clickedFill.reason}</p>
          <small>收盘信号日 {clickedFill.signal_date}</small>
        </aside>
      )}
    </div>
  );
}
