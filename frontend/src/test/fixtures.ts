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

// --- Revisions ---

import type { Comparison, History } from "../api/types";

export const comparison: Comparison = {
  assignment_id: 2,
  previous: { submission_id: 3, version_number: 1, grading_id: 7 },
  current: { submission_id: 4, version_number: 2, grading_id: 8 },
  overall: {
    previous_median: 8, current_median: 13, change: 5,
    previous_min: 5, previous_max: 9, current_min: 12, current_max: 14, max_possible: 16,
    ranges_overlap: false,
  },
  criteria: [
    {
      criterion_id: "thesis", name: "Thesis", max_points: 10, previous_points: 5, current_points: 10,
      change: 5, status: "improved", ranges_overlap: false, uncertain: false, resolved: true,
      issue: "The thesis is vague.",
    },
    {
      criterion_id: "support", name: "Evidence & Support", max_points: 6, previous_points: 3, current_points: 3,
      change: 0, status: "unchanged", ranges_overlap: true, uncertain: true, resolved: false,
      issue: "Evidence is general.",
    },
    {
      criterion_id: "style", name: "Style", max_points: 4, previous_points: 4, current_points: 3,
      change: -1, status: "declined", ranges_overlap: true, uncertain: false, resolved: false, issue: null,
    },
    {
      criterion_id: "extra", name: "Extra credit", max_points: 2, previous_points: null, current_points: 1,
      change: null, status: "new", ranges_overlap: false, uncertain: false, resolved: false, issue: null,
    },
  ],
  resolved_issues: [{ criterion_id: "thesis", name: "Thesis", issue: "The thesis is vague.", points_gained: 5 }],
  requirement_changes: [
    { description: "At least 50 words", previously_passed: false, now_passed: true, status: "resolved", details: "Draft has 80 words." },
    { description: "Include a conclusion", previously_passed: true, now_passed: false, status: "regressed", details: "Missing section(s): Conclusion." },
  ],
  remaining_fixes: [
    { criterion_id: "support", name: "Evidence & Support", points_at_stake: 3, summary: "Evidence is general." },
  ],
  improved_count: 1,
  declined_count: 1,
  unchanged_count: 1,
};

export const history: History = {
  assignment_id: 2,
  title: "Persuasive essay",
  max_possible: 16,
  criteria: [
    { criterion_id: "thesis", name: "Thesis", max_points: 10 },
    { criterion_id: "support", name: "Evidence & Support", max_points: 6 },
  ],
  versions: [
    {
      submission_id: 3, version_number: 1, created_at: "2026-10-15T10:00:00Z",
      grading: {
        grading_id: 7, overall: { median: 8, min: 5, max: 9, max_possible: 16 },
        criterion_points: { thesis: 5, support: 3 }, uncertain: ["support"],
      },
    },
    {
      submission_id: 4, version_number: 2, created_at: "2026-10-15T11:00:00Z",
      grading: {
        grading_id: 8, overall: { median: 13, min: 12, max: 14, max_possible: 16 },
        criterion_points: { thesis: 10, support: 3 }, uncertain: [],
      },
    },
    { submission_id: 5, version_number: 3, created_at: "2026-10-15T12:00:00Z", grading: null },
  ],
};
