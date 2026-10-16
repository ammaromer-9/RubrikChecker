import type { CriterionResult, Supports } from "../api/types";

export interface QuoteRef {
  criterionId: string;
  /** Index into that criterion's `evidence` array. */
  index: number;
  supports: Supports;
}

export interface Segment {
  text: string;
  /** Quotes covering this stretch of text, in the order they appear in the results. */
  refs: QuoteRef[];
}

export const quoteKey = (criterionId: string, index: number) => `${criterionId}:${index}`;

/**
 * Split the draft into plain and highlighted segments. Only verified evidence with
 * valid offsets is highlighted; overlapping quotes share the overlapping text.
 */
export function buildSegments(draft: string, criteria: CriterionResult[]): Segment[] {
  const spans: (QuoteRef & { start: number; end: number })[] = [];
  for (const criterion of criteria) {
    criterion.evidence.forEach((item, index) => {
      if (!item.verified || item.start === null || item.end === null) return;
      if (item.start < 0 || item.end > draft.length || item.end <= item.start) return;
      spans.push({
        criterionId: criterion.criterion_id,
        index,
        supports: item.supports,
        start: item.start,
        end: item.end,
      });
    });
  }

  const cuts = [...new Set([0, draft.length, ...spans.flatMap((s) => [s.start, s.end])])].sort(
    (a, b) => a - b,
  );
  const segments: Segment[] = [];
  for (let i = 0; i < cuts.length - 1; i++) {
    const [from, to] = [cuts[i], cuts[i + 1]];
    segments.push({
      text: draft.slice(from, to),
      refs: spans
        .filter((s) => s.start <= from && s.end >= to)
        .map(({ criterionId, index, supports }) => ({ criterionId, index, supports })),
    });
  }
  return segments;
}
