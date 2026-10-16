import type { CriterionResult, Grading } from "../api/types";

export const DRAFT =
  "Social media harms teen sleep. Many students scroll late at night.\n\nHowever, schools should not ban phones outright because families differ.";

const Q1 = "Social media harms teen sleep.";
const Q2 = "Many students scroll late at night.";
const Q3 = "schools should not ban phones outright";

const at = (quote: string) => {
  const start = DRAFT.indexOf(quote);
  return { quote, start, end: start + quote.length, verified: true };
};

export const thesis: CriterionResult = {
  criterion_id: "thesis",
  name: "Thesis",
  max_points: 10,
  median_points: 10,
  min_points: 5,
  max_points_scored: 10,
  uncertain: false,
  chosen_level: "Excellent",
  confidence: "high",
  reasoning: "The first sentence states a clear, arguable claim.",
  run_points: [10, 10, 5],
  evidence: [{ ...at(Q1), supports: "met" }],
  feedback: null,
};

export const support: CriterionResult = {
  criterion_id: "support",
  name: "Evidence & Support",
  max_points: 6,
  median_points: 3,
  min_points: 0,
  max_points_scored: 6,
  uncertain: true,
  chosen_level: "Some",
  confidence: "medium",
  reasoning: "Evidence is general; no specific study or statistic.",
  run_points: [3, 6, 0],
  evidence: [
    { ...at(Q2), supports: "not_met" },
    { quote: "Teenagers always sleep eight hours.", supports: "met", start: null, end: null, verified: false },
    { ...at(Q3), supports: "not_met" },
  ],
  feedback: {
    whats_missing: "The evidence is general rather than specific.",
    where_in_draft: "The first paragraph",
    evidence_indexes: [1, 2],
    guiding_questions: ["What specific study could you point to?"],
    is_fallback: false,
  },
};

export const grading: Grading = {
  id: 7,
  submission_id: 3,
  assignment_id: 2,
  version_number: 1,
  status: "complete",
  error: null,
  strategy: "per_criterion",
  model: "fake",
  num_runs: 3,
  prompt_version: "grade_criterion.v1+feedback.v1",
  created_at: "2026-10-15T12:00:00Z",
  overall: { median: 13, min: 5, max: 16, max_possible: 16 },
  draft_text: DRAFT,
  criteria: [thesis, support],
  instruction_checks: [
    {
      requirement: { type: "word_count", description: "At least 50 words", min_words: 50, max_words: null },
      passed: false,
      details: "Draft has 22 words. 28 words short of the 50-word minimum.",
    },
    {
      requirement: { type: "required_sections", description: "Include a conclusion", headings: ["Conclusion"] },
      passed: true,
      details: "All required sections found: Conclusion.",
    },
  ],
  top_fixes: [
    { criterion_id: "support", name: "Evidence & Support", points_at_stake: 3, summary: "The evidence is general rather than specific." },
  ],
};
