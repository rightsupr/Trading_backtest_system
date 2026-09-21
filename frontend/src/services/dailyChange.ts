import type { Bar } from "../types";

// pct_change is already in percentage points (1 means 1%, not 100%).
export function dailyChange(bar: Bar, previous?: Bar): number | null {
  if (bar.pct_change != null && Number.isFinite(bar.pct_change))
    return bar.pct_change;
  const prior =
    bar.pre_close != null && Number.isFinite(bar.pre_close) && bar.pre_close > 0
      ? bar.pre_close
      : previous?.close;
  if (
    prior == null ||
    !Number.isFinite(prior) ||
    prior <= 0 ||
    !Number.isFinite(bar.close)
  )
    return null;
  const change = (bar.close / prior - 1) * 100;
  return Number.isFinite(change) ? change : null;
}
