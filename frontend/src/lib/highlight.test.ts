import { describe, expect, it } from "vitest";

import type { CriterionResult, Evidence } from "../api/types";
import { DRAFT, support, thesis } from "../test/fixtures";
import { buildSegments } from "./highlight";

const criterion = (id: string, evidence: Evidence[]): CriterionResult => ({ ...thesis, criterion_id: id, evidence });
const ev = (start: number, end: number, supports: "met" | "not_met" = "met"): Evidence => ({
  quote: DRAFT.slice(start, end), supports, start, end, verified: true,
});

describe("buildSegments", () => {
  it("returns one plain segment when nothing is highlighted", () => {
    expect(buildSegments("hello world", [criterion("a", [])])).toEqual([{ text: "hello world", refs: [] }]);
  });

  it("splits the draft around a highlight and reassembles to the original text", () => {
    const segments = buildSegments(DRAFT, [thesis, support]);
    expect(segments.map((s) => s.text).join("")).toBe(DRAFT);
    const highlighted = segments.filter((s) => s.refs.length);
    expect(highlighted.map((s) => s.text)).toEqual([
      "Social media harms teen sleep.",
      "Many students scroll late at night.",
      "schools should not ban phones outright",
    ]);
    expect(highlighted[0].refs).toEqual([{ criterionId: "thesis", index: 0, supports: "met" }]);
    expect(highlighted[1].refs[0]).toEqual({ criterionId: "support", index: 0, supports: "not_met" });
  });

  it("ignores unverified quotes and invalid offsets", () => {
    const bad: Evidence[] = [
      { quote: "x", supports: "met", start: null, end: null, verified: false },
      { quote: "x", supports: "met", start: 5, end: 5, verified: true },
      { quote: "x", supports: "met", start: -1, end: 3, verified: true },
      { quote: "x", supports: "met", start: 0, end: DRAFT.length + 1, verified: true },
    ];
    expect(buildSegments(DRAFT, [criterion("a", bad)])).toEqual([{ text: DRAFT, refs: [] }]);
  });

  it("lets overlapping quotes share the overlapping text", () => {
    const segments = buildSegments("0123456789", [
      criterion("a", [{ ...ev(0, 6), quote: "012345" }]),
      criterion("b", [{ ...ev(4, 9, "not_met"), quote: "45678" }]),
    ]);
    expect(segments.map((s) => [s.text, s.refs.map((r) => r.criterionId)])).toEqual([
      ["0123", ["a"]],
      ["45", ["a", "b"]],
      ["678", ["b"]],
      ["9", []],
    ]);
  });

  it("handles a highlight at the very start and end", () => {
    const segments = buildSegments("abcdef", [criterion("a", [{ ...ev(0, 6), quote: "abcdef" }])]);
    expect(segments).toEqual([{ text: "abcdef", refs: [{ criterionId: "a", index: 0, supports: "met" }] }]);
  });
});
