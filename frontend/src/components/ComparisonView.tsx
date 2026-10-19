import { Link } from "react-router-dom";

import type { ChangeStatus, Comparison, RequirementStatus } from "../api/types";
import { fmt, fmtDelta } from "../lib/format";
import { strictnessLabel } from "../lib/strictness";
import { Badge } from "./ui";

const ARROWS: Record<ChangeStatus, { symbol: string; label: string; tone: string }> = {
  improved: { symbol: "▲", label: "improved", tone: "text-green-700" },
  declined: { symbol: "▼", label: "declined", tone: "text-red-700" },
  unchanged: { symbol: "–", label: "unchanged", tone: "text-slate-500" },
  new: { symbol: "+", label: "new criterion", tone: "text-slate-600" },
  removed: { symbol: "×", label: "removed criterion", tone: "text-slate-600" },
};

const REQUIREMENT_TEXT: Record<RequirementStatus, { text: string; tone: "green" | "red" | "slate" }> = {
  resolved: { text: "Now met", tone: "green" },
  regressed: { text: "No longer met", tone: "red" },
  still_failing: { text: "Still not met", tone: "red" },
  still_passing: { text: "Still met", tone: "slate" },
  new: { text: "New requirement", tone: "slate" },
  removed: { text: "No longer checked", tone: "slate" },
};

function Points({ value, max }: { value: number | null; max: number }) {
  return value === null ? <span className="text-slate-400">&ndash;</span> : <>{fmt(value)}<span className="text-slate-400"> / {fmt(max)}</span></>;
}

export default function ComparisonView({ comparison }: { comparison: Comparison }) {
  const { overall, previous, current } = comparison;
  const direction = overall.change > 0 ? "up" : overall.change < 0 ? "down" : "flat";

  return (
    <div className="space-y-6">
      <section aria-label="Overall change" className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <p className="text-sm uppercase tracking-wide text-slate-500">
          Attempt {previous.version_number} &rarr; attempt {current.version_number}
        </p>
        <p className="mt-1 text-3xl font-bold" data-testid="overall-change">
          {fmt(overall.previous_median)} &rarr; {fmt(overall.current_median)}
          <span className="text-xl font-normal text-slate-500"> / {fmt(overall.max_possible)}</span>
          <span className={`ml-3 text-xl ${direction === "up" ? "text-green-700" : direction === "down" ? "text-red-700" : "text-slate-500"}`}>
            ({fmtDelta(overall.change)})
          </span>
        </p>
        {direction !== "flat" && (
          <p className="mt-2 text-sm text-slate-700" data-testid="noise-note">
            {overall.ranges_overlap
              ? "The score ranges of the two attempts overlap, so part of this change may just be normal variation between grading runs. Treat it as a hint, not proof."
              : `The score ranges don't overlap, so this ${direction === "up" ? "improvement" : "drop"} is likely real.`}
          </p>
        )}
        {comparison.strictness_differs && (
          <p role="note" data-testid="strictness-warning" className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
            These attempts were graded for different teachers (attempt {previous.version_number}:{" "}
            {strictnessLabel(previous.strictness).toLowerCase()}, attempt {current.version_number}:{" "}
            {strictnessLabel(current.strictness).toLowerCase()}), so part of this change may come from that setting rather
            than from your edits. Grade one attempt again with the same setting for a fair comparison.
          </p>
        )}
        <p className="mt-2 flex flex-wrap gap-3 text-sm">
          <Link className="text-indigo-700 underline" to={`/gradings/${current.grading_id}`}>Full results for attempt {current.version_number}</Link>
          <Link className="text-indigo-700 underline" to={`/projects/${comparison.assignment_id}`}>All attempts</Link>
        </p>
      </section>

      {comparison.resolved_issues.length > 0 && (
        <section aria-label="Resolved issues" className="rounded-lg border border-green-200 bg-green-50 p-4">
          <h2 className="text-lg font-semibold text-green-950">Issues you fixed</h2>
          <ul className="mt-2 space-y-2 text-sm">
            {comparison.resolved_issues.map((issue) => (
              <li key={issue.criterion_id}>
                <p className="font-medium text-green-950">
                  &#10003; {issue.name} <Badge tone="green">+{fmt(issue.points_gained)} pts</Badge>
                </p>
                <p className="text-green-900">Was: {issue.issue}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Changes by criterion" className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">By criterion</h2>
        <p className="mt-1 text-sm text-slate-600">
          {comparison.improved_count} improved, {comparison.unchanged_count} unchanged, {comparison.declined_count} declined.
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[30rem] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="py-1 pr-3">Criterion</th>
                <th className="py-1 pr-3">Attempt {previous.version_number}</th>
                <th className="py-1 pr-3">Attempt {current.version_number}</th>
                <th className="py-1">Change</th>
              </tr>
            </thead>
            <tbody>
              {comparison.criteria.map((c) => {
                const arrow = ARROWS[c.status];
                return (
                  <tr key={c.criterion_id} className="border-t border-slate-100 align-top">
                    <th scope="row" className="py-2 pr-3 font-medium">{c.name}</th>
                    <td className="py-2 pr-3"><Points value={c.previous_points} max={c.max_points} /></td>
                    <td className="py-2 pr-3"><Points value={c.current_points} max={c.max_points} /></td>
                    <td className="py-2">
                      <span className={`font-medium ${arrow.tone}`}>
                        <span aria-hidden="true">{arrow.symbol}</span>
                        <span className="sr-only">{arrow.label}</span>{" "}
                        {c.change !== null ? fmtDelta(c.change) : arrow.label}
                      </span>
                      <span className="ml-2 inline-flex flex-wrap gap-1">
                        {c.resolved && <Badge tone="green">fixed</Badge>}
                        {c.uncertain && <Badge tone="amber">uncertain</Badge>}
                        {c.status !== "unchanged" && c.status !== "new" && c.status !== "removed" && c.ranges_overlap && (
                          <Badge tone="slate">within normal variation</Badge>
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {comparison.requirement_changes.length > 0 && (
        <section aria-label="Requirement changes" className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-lg font-semibold">Assignment requirements</h2>
          <ul className="mt-2 space-y-2 text-sm">
            {comparison.requirement_changes.map((r) => (
              <li key={r.description}>
                <span className="font-medium">{r.description}</span>{" "}
                <Badge tone={REQUIREMENT_TEXT[r.status].tone}>{REQUIREMENT_TEXT[r.status].text}</Badge>
                {r.status !== "still_passing" && r.status !== "removed" && <p className="text-slate-600">{r.details}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-label="Still to fix" className="rounded-lg border border-indigo-200 bg-indigo-50 p-4">
        <h2 className="text-lg font-semibold text-indigo-950">Still to fix</h2>
        {comparison.remaining_fixes.length === 0 ? (
          <p className="mt-1 text-sm text-indigo-900">Nothing is costing points in attempt {current.version_number}.</p>
        ) : (
          <ol className="mt-2 space-y-2 text-sm">
            {comparison.remaining_fixes.map((fix, i) => (
              <li key={fix.criterion_id}>
                <span className="font-semibold text-indigo-900">{i + 1}. {fix.name}</span>{" "}
                <Badge tone="amber">{fmt(fix.points_at_stake)} pts at stake</Badge>
                <p className="text-indigo-950">{fix.summary}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}
