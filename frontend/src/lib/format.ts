/** 8 -> "8", 7.5 -> "7.5", 7.333 -> "7.3" */
export function fmt(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, "");
}

/** "82/100, likely 78-86" (the range is omitted when it is a single value). */
export function formatOverall(o: { median: number | null; min: number | null; max: number | null; max_possible: number }): string {
  if (o.median === null) return "Not graded";
  const base = `${fmt(o.median)}/${fmt(o.max_possible)}`;
  if (o.min === null || o.max === null || o.min === o.max) return base;
  return `${base}, likely ${fmt(o.min)}–${fmt(o.max)}`;
}
