import type { Strictness } from "../api/types";

export const STRICTNESS_OPTIONS: { value: Strictness; label: string; description: string }[] = [
  { value: "lenient", label: "Lenient", description: "Gives credit for reasonable attempts and mostly-met descriptions." },
  { value: "standard", label: "Standard", description: "Grades exactly as the rubric reads, with no lean either way." },
  { value: "strict", label: "Strict", description: "Needs a level's description fully met before giving that level." },
];

export const strictnessLabel = (value: Strictness): string =>
  STRICTNESS_OPTIONS.find((o) => o.value === value)?.label ?? value;
