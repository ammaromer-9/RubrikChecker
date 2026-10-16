import { useState } from "react";

import type { Criterion, Level, Rubric } from "../api/types";
import { fmt } from "../lib/format";
import { Badge, Button, ErrorBanner, Spinner } from "./ui";

/** Mirrors the backend rubric validation so mistakes are caught before saving. */
export function validateRubric(rubric: Rubric): string[] {
  const problems: string[] = [];
  if (rubric.criteria.length === 0) problems.push("Add at least one criterion.");
  const ids = rubric.criteria.map((c) => c.id);
  for (const criterion of rubric.criteria) {
    const name = criterion.name.trim() || "(unnamed criterion)";
    if (!criterion.name.trim()) problems.push("Every criterion needs a name.");
    if (!(criterion.max_points > 0)) problems.push(`${name}: max points must be greater than 0.`);
    if (criterion.levels.length === 0) problems.push(`${name}: add at least one level.`);
    const labels = criterion.levels.map((l) => l.label.trim().toLowerCase());
    if (criterion.levels.some((l) => !l.label.trim())) problems.push(`${name}: every level needs a label.`);
    if (new Set(labels).size !== labels.length) problems.push(`${name}: level labels must be different.`);
    for (const level of criterion.levels) {
      if (level.points < 0) problems.push(`${name}: "${level.label}" has negative points.`);
      if (level.points > criterion.max_points)
        problems.push(`${name}: "${level.label}" is worth more than the criterion's max (${fmt(criterion.max_points)}).`);
    }
    if (ids.filter((id) => id === criterion.id).length > 1) problems.push(`${name}: duplicate criterion id.`);
  }
  return [...new Set(problems)];
}

function slugify(name: string, taken: string[]): string {
  const base = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "criterion";
  let id = base;
  for (let n = 2; taken.includes(id); n++) id = `${base}_${n}`;
  return id;
}

const field =
  "w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500";

interface Props {
  initial: Rubric;
  confirmed: boolean;
  saving: boolean;
  serverError: string | null;
  onConfirm: (rubric: Rubric) => void;
}

export default function RubricEditor({ initial, confirmed, saving, serverError, onConfirm }: Props) {
  const [rubric, setRubric] = useState<Rubric>(initial);
  const problems = validateRubric(rubric);
  const total = rubric.criteria.reduce((sum, c) => sum + (Number.isFinite(c.max_points) ? c.max_points : 0), 0);
  const hasInferred = rubric.criteria.some((c) => c.levels.some((l) => l.inferred));

  const updateCriterion = (index: number, patch: Partial<Criterion>) =>
    setRubric((r) => ({ criteria: r.criteria.map((c, i) => (i === index ? { ...c, ...patch } : c)) }));

  // Editing a level counts as reviewing it, so it stops being flagged as inferred.
  const updateLevel = (ci: number, li: number, patch: Partial<Level>) =>
    updateCriterion(ci, {
      levels: rubric.criteria[ci].levels.map((l, i) => (i === li ? { ...l, ...patch, inferred: false } : l)),
    });

  const addCriterion = () =>
    setRubric((r) => ({
      criteria: [
        ...r.criteria,
        {
          id: slugify("new criterion", r.criteria.map((c) => c.id)),
          name: "New criterion",
          max_points: 10,
          levels: [{ label: "Full credit", points: 10, description: "", inferred: false }],
        },
      ],
    }));

  return (
    <div className="space-y-6">
      {hasInferred && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Some levels were <strong>inferred</strong>: your rubric did not spell them out, so the AI suggested them. Check
          them carefully. Editing a level marks it as reviewed.
        </div>
      )}

      {rubric.criteria.map((criterion, ci) => (
        <section key={ci} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm" aria-label={`Criterion ${criterion.name}`}>
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-0 flex-1 text-sm font-medium text-slate-700">
              Criterion name
              <input className={`${field} mt-1`} value={criterion.name} onChange={(e) => updateCriterion(ci, { name: e.target.value })} />
            </label>
            <label className="w-28 text-sm font-medium text-slate-700">
              Max points
              <input
                className={`${field} mt-1`}
                type="number"
                min={0}
                step="any"
                value={criterion.max_points}
                onChange={(e) => updateCriterion(ci, { max_points: e.target.valueAsNumber || 0 })}
              />
            </label>
            <Button variant="danger" onClick={() => setRubric((r) => ({ criteria: r.criteria.filter((_, i) => i !== ci) }))}>
              Remove criterion
            </Button>
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[32rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="w-40 py-1 pr-2">Level</th>
                  <th className="w-24 py-1 pr-2">Points</th>
                  <th className="py-1 pr-2">Description</th>
                  <th className="w-20" />
                </tr>
              </thead>
              <tbody>
                {criterion.levels.map((level, li) => (
                  <tr key={li} className="align-top">
                    <td className="py-1 pr-2">
                      <input aria-label="Level label" className={field} value={level.label} onChange={(e) => updateLevel(ci, li, { label: e.target.value })} />
                      {level.inferred && <div className="mt-1"><Badge tone="amber">inferred</Badge></div>}
                    </td>
                    <td className="py-1 pr-2">
                      <input
                        aria-label="Level points"
                        className={field}
                        type="number"
                        min={0}
                        step="any"
                        value={level.points}
                        onChange={(e) => updateLevel(ci, li, { points: e.target.valueAsNumber || 0 })}
                      />
                    </td>
                    <td className="py-1 pr-2">
                      <textarea aria-label="Level description" rows={2} className={field} value={level.description} onChange={(e) => updateLevel(ci, li, { description: e.target.value })} />
                    </td>
                    <td className="py-1">
                      <button
                        type="button"
                        className="text-xs text-red-700 hover:underline"
                        onClick={() => updateCriterion(ci, { levels: criterion.levels.filter((_, i) => i !== li) })}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button
            variant="secondary"
            className="mt-2"
            onClick={() => updateCriterion(ci, { levels: [...criterion.levels, { label: "", points: 0, description: "", inferred: false }] })}
          >
            Add level
          </Button>
        </section>
      ))}

      <Button variant="secondary" onClick={addCriterion}>Add criterion</Button>

      <div className="sticky bottom-0 -mx-4 border-t border-slate-200 bg-white/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-lg sm:border">
        {problems.length > 0 && (
          <ul className="mb-3 list-disc space-y-0.5 pl-5 text-sm text-red-700" aria-label="Rubric problems">
            {problems.map((p) => <li key={p}>{p}</li>)}
          </ul>
        )}
        <ErrorBanner message={serverError} />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <span className="text-sm text-slate-600">
            {rubric.criteria.length} criteria &middot; {fmt(total)} points total
            {confirmed && " · currently confirmed"}
          </span>
          <Button disabled={problems.length > 0 || saving} onClick={() => onConfirm(rubric)}>
            {saving && <Spinner className="h-4 w-4" />}
            Confirm rubric
          </Button>
        </div>
      </div>
    </div>
  );
}
