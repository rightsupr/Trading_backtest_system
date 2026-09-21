import type { Bar, Run } from "../types";
import { dailyChange } from "../services/dailyChange";

export interface Plot {
  key: string;
  label: string;
  pane: string;
  color: string;
  values: (number | null)[];
  line: boolean;
  value: boolean;
  kind?: "histogram";
  format?: "percent" | "volume";
  basic?: boolean;
}
export interface PlotPreference {
  line: boolean;
  value: boolean;
  pane: string;
  color: string;
}
export interface ChartPreferences {
  overrides: Record<string, Partial<PlotPreference>>;
  averages: { kind: "MA" | "EMA"; period: number }[];
}
export const emptyPreferences = (): ChartPreferences => ({
  overrides: {},
  averages: [],
});
export function readChartPreferences(): ChartPreferences {
  try {
    const value = JSON.parse(localStorage.getItem("quant.chart.v1") ?? "null");
    if (
      !value ||
      typeof value.overrides !== "object" ||
      !value.overrides ||
      !Array.isArray(value.averages)
    )
      return emptyPreferences();
    return {
      overrides: value.overrides,
      averages: value.averages
        .filter(
          (a: { kind: string; period: number }) =>
            a &&
            ["MA", "EMA"].includes(a.kind) &&
            Number.isInteger(a.period) &&
            a.period >= 1 &&
            a.period <= 500,
        )
        .slice(0, 20),
    };
  } catch {
    return emptyPreferences();
  }
}
const numeric = (v: unknown): number | null =>
  typeof v === "number" && Number.isFinite(v) ? v : null;
export function movingAverage(
  bars: Bar[],
  period: number,
  kind: "MA" | "EMA",
): (number | null)[] {
  let sum = 0,
    previous = bars[0]?.close ?? 0;
  return bars.map((b, i) => {
    sum += b.close;
    if (i >= period) sum -= bars[i - period].close;
    previous =
      i === 0
        ? b.close
        : (2 / (period + 1)) * b.close + (1 - 2 / (period + 1)) * previous;
    return i + 1 < period ? null : kind === "MA" ? sum / period : previous;
  });
}
export function indicatorCatalog(
  bars: Bar[],
  run: Run | null,
  prefs: ChartPreferences,
): Plot[] {
  const plots: Plot[] = [];
  const add = (
    key: string,
    label: string,
    pane: string,
    color: string,
    line = false,
    value = false,
    extras: Partial<Plot> = {},
  ) =>
    plots.push({
      key,
      label,
      pane,
      color,
      line,
      value,
      values: bars.map((b) => numeric(b[key])),
      ...extras,
    });
  for (const [key, label] of [
    ["open", "开"],
    ["high", "高"],
    ["low", "低"],
    ["close", "收"],
  ])
    add(key, label, "price", "#536375", false, true, { basic: true });
  add("daily_change", "涨跌幅", "变化", "#536375", false, true, {
    basic: true,
    format: "percent",
    values: bars.map((b, i) => dailyChange(b, bars[i - 1])),
  });
  const ma =
    run &&
    !run.request.custom_strategy &&
    run.request.strategy_name === "ma_cross";
  add(
    ma ? "strategy_fast" : "sma_5",
    ma ? `MA${run.request.parameters.fast_ma}（策略）` : "MA5",
    "price",
    "#d6a148",
    true,
    true,
  );
  add(
    ma ? "strategy_slow" : "sma_20",
    ma ? `MA${run.request.parameters.slow_ma}（策略）` : "MA20",
    "price",
    "#718bc3",
    true,
    true,
  );
  add("volume", "成交量", "成交量", "#15947c", true, false, {
    kind: "histogram",
    format: "volume",
  });
  add("volume_ma", "量均线5", "成交量", "#d6a148", false, false, {
    format: "volume",
  });
  add("macd_dif", "DIF", "MACD", "#d6a148", true, false);
  add("macd_dea", "DEA", "MACD", "#718bc3", true, false);
  add("macd_hist", "MACD 柱", "MACD", "#15947c", true, false, {
    kind: "histogram",
  });
  for (const [key, label, pane, color] of [
    ["boll_upper", "BOLL 上轨20", "price", "#8b6cc1"],
    ["boll_mid", "BOLL 中轨20", "price", "#d6a148"],
    ["boll_lower", "BOLL 下轨20", "price", "#8b6cc1"],
    ["rsi", "RSI14", "RSI", "#8b6cc1"],
    ["atr", "ATR14", "ATR", "#dd875b"],
    ["kdj_k", "K", "KDJ", "#d6a148"],
    ["kdj_d", "D", "KDJ", "#718bc3"],
    ["kdj_j", "J", "KDJ", "#8b6cc1"],
    ["dif_slope", "DIF 斜率", "斜率", "#d6a148"],
    ["dea_slope", "DEA 斜率", "斜率", "#718bc3"],
    ["amount", "成交额", "成交额", "#718bc3"],
    ["turnover", "换手率", "换手率", "#dd875b"],
  ])
    add(key, label, pane, color);
  for (const a of prefs.averages)
    add(
      `custom:${a.kind}:${a.period}`,
      `${a.kind}${a.period}`,
      "price",
      a.kind === "MA" ? "#b17bc0" : "#529aaa",
      true,
      true,
      { values: movingAverage(bars, a.period, a.kind) },
    );
  for (const series of run?.chart_series ?? []) {
    if (series.values.length !== bars.length) continue;
    plots.push({
      ...series,
      values: series.values.map(numeric),
      line: true,
      value: true,
    });
  }
  return plots.map((p) => {
    const o = prefs.overrides[p.key];
    if (!o || typeof o !== "object") return p;
    return {
      ...p,
      line: typeof o.line === "boolean" ? o.line : p.line,
      value: typeof o.value === "boolean" ? o.value : p.value,
      pane: typeof o.pane === "string" && o.pane.length <= 60 ? o.pane : p.pane,
      color:
        typeof o.color === "string" && /^#[0-9a-f]{6}$/i.test(o.color)
          ? o.color
          : p.color,
    };
  });
}
export function displayValue(plot: Plot, index: number): string {
  const value = plot.values[index];
  if (value == null || !Number.isFinite(value)) return "—";
  if (plot.format === "percent")
    return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
  return value.toLocaleString("zh-CN", {
    maximumFractionDigits: plot.format === "volume" ? 0 : 3,
  });
}
