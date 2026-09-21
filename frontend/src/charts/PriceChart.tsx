import { useEffect, useMemo, useRef, useState } from "react";
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
  LogicalRange,
} from "lightweight-charts";
import type { Bar, Fill, Run, Trade } from "../types";
import { percent } from "../services/api";
import ChartSettings from "../components/ChartSettings";
import {
  indicatorCatalog,
  readChartPreferences,
  displayValue,
} from "./indicatorCatalog";

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
  const [paneLabels, setPaneLabels] = useState<
    { label: string; top: number }[]
  >([]);
  const [plotWidth, setPlotWidth] = useState(0);
  const [clickedFill, setClickedFill] = useState<Fill | null>(null);
  const [preferences, setPreferences] = useState(readChartPreferences);
  const [settingsError, setSettingsError] = useState("");
  const plots = useMemo(
    () => indicatorCatalog(bars, run, preferences),
    [bars, run, preferences],
  );
  const plotSignature = JSON.stringify(
    plots.map((p) => [p.key, p.line, p.pane, p.color]),
  );
  const plotsRef = useRef(plots);
  plotsRef.current = plots;
  const lastBars = useRef(bars);
  const savedRange = useRef<LogicalRange | null>(null);
  useEffect(() => {
    try {
      localStorage.setItem("quant.chart.v1", JSON.stringify(preferences));
      setSettingsError("");
    } catch {
      setSettingsError("图表设置暂时无法保存，当前显示仍然有效。");
    }
  }, [preferences]);

  useEffect(() => {
    setHover(null);
    if (!host.current || bars.length === 0) return;
    setClickedFill(null);
    const visiblePlots = plotsRef.current.filter((p) => p.line);
    const paneNames = [
      ...new Set(visiblePlots.map((p) => p.pane).filter((p) => p !== "price")),
    ];
    const previousRange = lastBars.current === bars ? savedRange.current : null;
    lastBars.current = bars;
    const chart = createChart(host.current, {
      autoSize: true,
      height: 390 + paneNames.length * 130,
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
    for (const plot of visiblePlots) {
      const pane = plot.pane === "price" ? 0 : paneNames.indexOf(plot.pane) + 1;
      const series = chart.addSeries(
        plot.kind === "histogram" ? HistogramSeries : LineSeries,
        {
          color: plot.color,
          priceLineVisible: false,
          lastValueVisible: false,
          lineWidth: 1,
          priceFormat:
            plot.format === "volume"
              ? { type: "volume" }
              : { type: "price", precision: 3, minMove: 0.001 },
        },
        pane,
      );
      series.setData(
        bars.map((b, i) => {
          const value = plot.values[i];
          if (value == null || !Number.isFinite(value)) return { time: b.date };
          const sign = plot.key === "volume" ? b.close - b.open : value;
          return {
            time: b.date,
            value,
            ...(plot.kind === "histogram"
              ? { color: sign >= 0 ? "#d75d6299" : `${plot.color}99` }
              : {}),
          };
        }),
      );
    }
    chart
      .panes()
      .forEach((pane, i) => pane.setStretchFactor(i === 0 ? 350 : 120));
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
        let top = chart.panes()[0].getHeight() + 43;
        setPaneLabels(
          paneNames.map((label, i) => {
            const entry = { label, top };
            top += chart.panes()[i + 1]?.getHeight() ?? 0;
            return entry;
          }),
        );
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
    if (previousRange) chart.timeScale().setVisibleLogicalRange(previousRange);
    else chart.timeScale().fitContent();
    draw();
    return () => {
      savedRange.current = chart.timeScale().getVisibleLogicalRange();
      observer.disconnect();
      cancelAnimationFrame(raf);
      markerPlugin.detach();
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, run, plotSignature]);

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
  }, [selected, bars, plotSignature]);

  const current = hover && bars.includes(hover) ? hover : bars.at(-1);
  const currentIndex = current ? bars.indexOf(current) : -1;
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
    <>
      <ChartSettings
        plots={plots}
        preferences={preferences}
        onChange={setPreferences}
      />
      {settingsError && <p role="status">{settingsError}</p>}
      <div className="price-chart">
        <div className="chart-legend">
          <strong>{current?.date}</strong>
          {plots
            .filter((p) => p.value)
            .map((plot) => {
              const number = plot.values[currentIndex];
              return (
                <span
                  key={plot.key}
                  className={
                    plot.key === "daily_change"
                      ? "daily-change"
                      : "indicator-value"
                  }
                >
                  {plot.label}{" "}
                  <b
                    style={{
                      color:
                        plot.format === "percent" && number != null
                          ? number > 0
                            ? "#ca555e"
                            : number < 0
                              ? "#168b77"
                              : plot.color
                          : plot.color,
                    }}
                  >
                    {displayValue(plot, currentIndex)}
                  </b>
                </span>
              );
            })}
          <button
            className="text-button"
            onClick={() => chartRef.current?.timeScale().fitContent()}
          >
            显示全部
          </button>
        </div>
        <div
          className="chart-canvas"
          ref={host}
          style={{
            height:
              390 +
              new Set(
                plots
                  .filter((p) => p.line && p.pane !== "price")
                  .map((p) => p.pane),
              ).size *
                130,
          }}
        />
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
        {paneLabels.map((pane) => (
          <span
            key={pane.label}
            className="pane-label"
            style={{ top: pane.top }}
          >
            {pane.label}
          </span>
        ))}
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
              {run?.request.strategy_name} ·{" "}
              {clickedFill.shares.toLocaleString()} 股
            </span>
            <p>{clickedFill.reason}</p>
            <small>收盘信号日 {clickedFill.signal_date}</small>
          </aside>
        )}
      </div>
    </>
  );
}
