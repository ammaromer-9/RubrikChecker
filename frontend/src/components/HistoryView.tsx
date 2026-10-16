import { Link } from "react-router-dom";

import type { History } from "../api/types";
import { fmt, fmtDelta, formatOverall } from "../lib/format";
import ScoreTrend from "./ScoreTrend";

export default function HistoryView({ history }: { history: History }) {
  const graded = history.versions.filter((v) => v.grading !== null);
  const maxPossible = history.max_possible ?? 0;
  const first = graded[0]?.grading;
  const last = graded[graded.length - 1]?.grading;

  // Previous graded version for each version (to diff against).
  const previousOf = new Map<number, (typeof graded)[number]>();
  graded.forEach((v, i) => i > 0 && previousOf.set(v.submission_id, graded[i - 1]));

  return (
    <div className="space-y-6">
      <section aria-label="Score trend" className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold">Score trend</h2>
        {graded.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">No version has been graded yet.</p>
        ) : (
          <>
            {graded.length > 1 && first && last && first.overall.median !== null && last.overall.median !== null ? (
              <p className="mt-1 text-sm text-slate-700" data-testid="trend-summary">
                {fmt(first.overall.median)} &rarr; {fmt(last.overall.median)} out of {fmt(maxPossible)} across {graded.length} versions
                ({fmtDelta(last.overall.median - first.overall.median)}).
              </p>
            ) : (
              <p className="mt-1 text-sm text-slate-600">Submit another version to see how your score changes.</p>
            )}
            <div className="mt-3">
              <ScoreTrend
                maxPossible={maxPossible}
                points={graded.map((v) => ({
                  label: `v${v.version_number}`,
                  median: v.grading!.overall.median ?? 0,
                  min: v.grading!.overall.min ?? 0,
                  max: v.grading!.overall.max ?? 0,
                }))}
              />
            </div>
            <p className="mt-1 text-xs text-slate-500">Dots show the predicted score; bars show the likely range.</p>
          </>
        )}
      </section>

      <section aria-label="Versions" className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Versions</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[28rem] text-left text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-slate-500">
                <th className="py-1 pr-3">Criterion</th>
                {history.versions.map((v) => (
                  <th key={v.submission_id} className="px-2 py-1 align-bottom">
                    {v.grading ? (
                      <Link className="text-indigo-700 underline" to={`/gradings/${v.grading.grading_id}`}>V{v.version_number}</Link>
                    ) : (
                      <span>V{v.version_number}</span>
                    )}
                    {previousOf.has(v.submission_id) && (
                      <div className="mt-0.5 normal-case">
                        <Link
                          className="text-xs text-indigo-700 underline"
                          to={`/submissions/${v.submission_id}/compare/${previousOf.get(v.submission_id)!.submission_id}`}
                        >
                          Compare with V{previousOf.get(v.submission_id)!.version_number}
                        </Link>
                      </div>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-slate-200 font-semibold">
                <th scope="row" className="py-2 pr-3">Overall</th>
                {history.versions.map((v) => {
                  const before = previousOf.get(v.submission_id)?.grading?.overall.median;
                  const now = v.grading?.overall.median;
                  return (
                    <td key={v.submission_id} className="px-2 py-2" data-testid={`overall-v${v.version_number}`}>
                      {v.grading ? formatOverall(v.grading.overall) : <span className="font-normal text-slate-400">Not graded</span>}
                      {before != null && now != null && <Delta change={now - before} />}
                    </td>
                  );
                })}
              </tr>
              {history.criteria.map((criterion) => (
                <tr key={criterion.criterion_id} className="border-t border-slate-100">
                  <th scope="row" className="py-2 pr-3 font-medium">{criterion.name}</th>
                  {history.versions.map((v) => {
                    const points = v.grading?.criterion_points[criterion.criterion_id];
                    const before = previousOf.get(v.submission_id)?.grading?.criterion_points[criterion.criterion_id];
                    return (
                      <td key={v.submission_id} className="px-2 py-2" data-testid={`${criterion.criterion_id}-v${v.version_number}`}>
                        {points === undefined ? (
                          <span className="text-slate-400">&ndash;</span>
                        ) : (
                          <>
                            {fmt(points)}<span className="text-slate-400"> / {fmt(criterion.max_points)}</span>
                            {v.grading!.uncertain.includes(criterion.criterion_id) && <span title="Grading runs disagreed" className="ml-1 text-amber-600">~</span>}
                            {before !== undefined && <Delta change={points - before} />}
                          </>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-500">~ means the grading runs disagreed on that criterion, so treat small changes there with caution.</p>
      </section>

      <p>
        <Link className="inline-block rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700" to={`/assignments/${history.assignment_id}/submit`}>
          Submit a new version
        </Link>
      </p>
    </div>
  );
}

function Delta({ change }: { change: number }) {
  if (Math.abs(change) < 1e-9) return <span className="ml-1 text-xs text-slate-400">(0)</span>;
  const up = change > 0;
  return (
    <span className={`ml-1 text-xs font-medium ${up ? "text-green-700" : "text-red-700"}`}>
      <span aria-hidden="true">{up ? "▲" : "▼"}</span>
      <span className="sr-only">{up ? "up" : "down"}</span> {fmtDelta(change)}
    </span>
  );
}
