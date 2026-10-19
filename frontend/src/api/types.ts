// Mirrors the backend Pydantic schemas (backend/app/schemas).

export interface User {
  id: number;
  email: string;
  display_name: string;
  created_at: string;
}

export interface ProjectSummary {
  id: number;
  title: string;
  created_at: string;
  rubric_confirmed: boolean;
  teacher_strictness: Strictness;
  attempts: number;
  graded_attempts: number;
  /** The newest graded attempt, with the change from the graded attempt before it. */
  latest: {
    version_number: number;
    median: number;
    min: number;
    max: number;
    max_possible: number;
    change: number | null;
  } | null;
}

export type Strictness = "lenient" | "standard" | "strict";

export interface Level {
  label: string;
  points: number;
  description: string;
  inferred: boolean;
}

export interface Criterion {
  id: string;
  name: string;
  max_points: number;
  levels: Level[];
}

export interface Rubric {
  criteria: Criterion[];
}

export type Requirement =
  | { type: "word_count"; description: string; min_words: number | null; max_words: number | null }
  | { type: "required_sections"; description: string; headings: string[] }
  | { type: "min_citations"; description: string; count: number }
  | { type: "citation_style"; description: string; style: string };

export interface Assignment {
  id: number;
  title: string;
  instructions_text: string;
  rubric_raw_text: string;
  rubric_parsed: Rubric | null;
  rubric_confirmed: boolean;
  requirements_parsed: { requirements: Requirement[] } | null;
  teacher_strictness: Strictness;
  created_at: string;
}

export interface NewAssignment {
  title: string;
  instructions_text: string;
  rubric_raw_text: string;
}

export interface Submission {
  id: number;
  assignment_id: number;
  version_number: number;
  draft_text: string;
  created_at: string;
}

export type Supports = "met" | "not_met";

export interface Evidence {
  quote: string;
  supports: Supports;
  /** Character offsets into the draft; null when the quote could not be verified. */
  start: number | null;
  end: number | null;
  verified: boolean;
}

export interface Feedback {
  whats_missing: string;
  where_in_draft: string;
  evidence_indexes: number[];
  guiding_questions: string[];
  is_fallback: boolean;
}

export interface CriterionResult {
  criterion_id: string;
  name: string;
  max_points: number;
  median_points: number;
  min_points: number;
  max_points_scored: number;
  uncertain: boolean;
  chosen_level: string | null;
  confidence: string | null;
  reasoning: string;
  run_points: number[];
  evidence: Evidence[];
  feedback: Feedback | null;
}

export interface CheckResult {
  requirement: Requirement;
  passed: boolean;
  details: string;
}

export interface TopFix {
  criterion_id: string;
  name: string;
  points_at_stake: number;
  summary: string;
}

export interface Grading {
  id: number;
  submission_id: number;
  assignment_id: number;
  version_number: number;
  status: string;
  error: string | null;
  strategy: string;
  model: string;
  num_runs: number;
  prompt_version: string;
  strictness: Strictness;
  created_at: string;
  overall: { median: number | null; min: number | null; max: number | null; max_possible: number };
  draft_text: string;
  criteria: CriterionResult[];
  instruction_checks: CheckResult[];
  top_fixes: TopFix[];
}

// --- Revisions ---

export interface VersionRef {
  submission_id: number;
  version_number: number;
  grading_id: number;
  strictness: Strictness;
}

export type ChangeStatus = "improved" | "declined" | "unchanged" | "new" | "removed";

export interface CriterionChange {
  criterion_id: string;
  name: string;
  max_points: number;
  previous_points: number | null;
  current_points: number | null;
  change: number | null;
  status: ChangeStatus;
  ranges_overlap: boolean;
  uncertain: boolean;
  resolved: boolean;
  issue: string | null;
}

export type RequirementStatus = "resolved" | "regressed" | "still_failing" | "still_passing" | "new" | "removed";

export interface RequirementChange {
  description: string;
  previously_passed: boolean | null;
  now_passed: boolean | null;
  status: RequirementStatus;
  details: string;
}

export interface Comparison {
  assignment_id: number;
  previous: VersionRef;
  current: VersionRef;
  overall: {
    previous_median: number;
    current_median: number;
    change: number;
    previous_min: number;
    previous_max: number;
    current_min: number;
    current_max: number;
    max_possible: number;
    ranges_overlap: boolean;
  };
  criteria: CriterionChange[];
  resolved_issues: { criterion_id: string; name: string; issue: string; points_gained: number }[];
  requirement_changes: RequirementChange[];
  remaining_fixes: TopFix[];
  /** The two versions were graded with different teacher strictness. */
  strictness_differs: boolean;
  improved_count: number;
  declined_count: number;
  unchanged_count: number;
}

export interface HistoryVersion {
  submission_id: number;
  version_number: number;
  created_at: string;
  grading: {
    grading_id: number;
    overall: Grading["overall"];
    criterion_points: Record<string, number>;
    uncertain: string[];
    strictness: Strictness;
  } | null;
}

export interface History {
  assignment_id: number;
  title: string;
  max_possible: number | null;
  criteria: { criterion_id: string; name: string; max_points: number }[];
  versions: HistoryVersion[];
}
