import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import type { CheckResult, Grading } from "../api/types";
import { fmt, formatOverall } from "../lib/format";
import { quoteKey, type QuoteRef } from "../lib/highlight";
import CriterionCard from "./CriterionCard";
import HighlightedDraft from "./HighlightedDraft";
import { Badge } from "./ui";

function InstructionChecklist({ checks }: { checks: CheckResult[] }) {
  if (checks.length === 0) return null;
  return (
    <section aria-label="Instruction checks" className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-lg font-semibold">Assignment requirements</h2>
      <ul className="mt-2 space-y-2">
        {checks.map((check, i) => (
          <li key={i} className="flex gap-2 text-sm">
            <span aria-hidden="true" className={check.passed ? "text-green-600" : "text-red-600"}>
              {check.passed ? "✓" : "✗"}
            </span>
            <div>
              <p className="font-medium">
                {check.requirement.description}
                <span className="sr-only">{check.passed ? " (met)" : " (not met)"}</span>
              </p>
              <p className="text-slate-600">{check.details}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function ResultsView({ grading }: { grading: Grading }) {
  const draftRef = useRef<HTMLDivElement>(null);
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    if (!flash) return;
    const timer = setTimeout(() => setFlash(null), 1800);
    return () => clearTimeout(timer);
  }, [flash]);

  const scrollOpts: ScrollIntoViewOptions = { behavior: "smooth", block: "center" };

  function goToCriterion(criterionId: string) {
    document.getElementById(`criterion-${criterionId}`)?.scrollIntoView(scrollOpts);
    setFlash(`criterion:${criterionId}`);
  }

  function goToQuote(criterionId: string, index: number) {
    const key = quoteKey(criterionId, index);
    draftRef.current?.querySelector(`[data-quotes~="${key}"]`)?.scrollIntoView(scrollOpts);
    setFlash(`quote:${key}`);
  }

  const flashQuote = flash?.startsWith("quote:") ? flash.slice(6) : null;
  const uncertainCount = grading.criteria.filter((c) => c.uncertain).length;

  return (
    <div className="space-y-6">
      <section aria-label="Overall score" className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <p className="text-sm uppercase tracking-wide text-slate-500">Predicted score &middot; version {grading.version_number}</p>
        <p className="mt-1 text-3xl font-bold" data-testid="overall">{formatOverall(grading.overall)}</p>
        <p className="mt-2 text-sm text-slate-600">
          A prediction from {grading.num_runs} independent grading run{grading.num_runs === 1 ? "" : "s"} per criterion, not your real grade.
          {uncertainCount > 0 && ` ${uncertainCount} criteri${uncertainCount === 1 ? "on is" : "a are"} marked uncertain.`}
        </p>
        <div className="mt-3">
          <Link className="text-sm text-indigo-700 underline" to={`/assignments/${grading.assignment_id}/submit`}>
            Submit a new version
          </Link>
        </div>
      </section>

      {grading.top_fixes.length > 0 && (
        <section aria-label="Top fixes" className="rounded-lg border border-indigo-200 bg-indigo-50 p-4">
          <h2 className="text-lg font-semibold text-indigo-950">Top {grading.top_fixes.length} things to fix first</h2>
          <ol className="mt-2 space-y-2">
            {grading.top_fixes.map((fix, i) => (
              <li key={fix.criterion_id} className="flex gap-3 text-sm">
                <span className="font-bold text-indigo-700">{i + 1}.</span>
                <div>
                  <button type="button" className="font-semibold text-indigo-900 underline" onClick={() => goToCriterion(fix.criterion_id)}>
                    {fix.name}
                  </button>
                  <span className="ml-2"><Badge tone="amber">{fmt(fix.points_at_stake)} pts at stake</Badge></span>
                  <p className="mt-0.5 text-indigo-950">{fix.summary}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      <InstructionChecklist checks={grading.instruction_checks} />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Scores by criterion</h2>
          {grading.criteria.map((result) => (
            <CriterionCard
              key={result.criterion_id}
              result={result}
              flashing={flash === `criterion:${result.criterion_id}`}
              onQuoteClick={(index) => goToQuote(result.criterion_id, index)}
            />
          ))}
        </div>

        <aside className="lg:sticky lg:top-4 lg:self-start" aria-label="Your draft">
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-lg font-semibold">Your draft</h2>
            <p className="mt-1 flex flex-wrap gap-3 text-xs text-slate-600">
              <span><span className="mr-1 inline-block h-3 w-3 rounded-sm bg-green-200 align-middle" />meets a criterion</span>
              <span><span className="mr-1 inline-block h-3 w-3 rounded-sm bg-red-200 align-middle" />falls short</span>
              <span>Click a highlight to jump to its criterion.</span>
            </p>
            <div className="mt-3 max-h-[70vh] overflow-y-auto pr-1">
              <HighlightedDraft
                ref={draftRef}
                draft={grading.draft_text}
                criteria={grading.criteria}
                flashQuote={flashQuote}
                onQuoteClick={(ref: QuoteRef) => goToCriterion(ref.criterionId)}
              />
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
