import type { Strictness } from "../api/types";
import { STRICTNESS_OPTIONS } from "../lib/strictness";

interface Props {
  value: Strictness;
  onChange: (value: Strictness) => void;
  disabled?: boolean;
  /** Distinguishes the radio group when more than one is on a page. */
  name?: string;
}

/** "How tough is your teacher?": a nudge for borderline calls; the rubric stays the standard. */
export default function StrictnessPicker({ value, onChange, disabled = false, name = "strictness" }: Props) {
  return (
    <fieldset disabled={disabled} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <legend className="px-1 text-sm font-semibold text-slate-800">How tough is your teacher when grading?</legend>
      <div className="mt-1 grid gap-2 sm:grid-cols-3">
        {STRICTNESS_OPTIONS.map((option) => (
          <label
            key={option.value}
            className={`flex cursor-pointer gap-2 rounded-md border p-3 text-sm ${
              value === option.value ? "border-indigo-500 bg-indigo-50" : "border-slate-200 hover:bg-slate-50"
            }`}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="mt-1"
            />
            <span>
              <span className="block font-medium text-slate-900">{option.label}</span>
              <span className="block text-slate-600">{option.description}</span>
            </span>
          </label>
        ))}
      </div>
      <p className="mt-3 text-xs text-slate-500">
        This only nudges borderline calls, where a draft sits between two levels. It can&apos;t change your rubric, and it
        isn&apos;t a promise to match your teacher.
      </p>
    </fieldset>
  );
}
