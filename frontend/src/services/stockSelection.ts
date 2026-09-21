import type { Query, SavedStock } from "../types";

// Compare versions of one stock. Keep the requested adjustment where available,
// and never let synthetic data outrank an existing real-data cache.
export function chooseSavedStock(
  stocks: SavedStock[],
  preferred: Pick<Query, "source" | "adjust">,
): SavedStock | undefined {
  const available = stocks.filter((s) => s.bars > 0);
  const real = available.filter((s) => s.source !== "sample");
  const candidates = real.length ? real : available;
  const matching = candidates.filter((s) => s.adjust === preferred.adjust);
  const health = (s: SavedStock) =>
    s.status === "refresh_required"
      ? 3
      : s.status === "error"
        ? 2
        : s.status === "success"
          ? 0
          : 1;
  return [...(matching.length ? matching : candidates)].sort(
    (a, b) =>
      b.end_date.localeCompare(a.end_date) ||
      health(a) - health(b) ||
      Number(b.source === preferred.source) -
        Number(a.source === preferred.source) ||
      a.source.localeCompare(b.source) ||
      a.adjust.localeCompare(b.adjust),
  )[0];
}
