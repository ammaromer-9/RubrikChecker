import type { CriterionResult } from "../api/types";
import { fmt } from "../lib/format";
import { Badge } from "./ui";

interface Props {
  result: CriterionResult;
  flashing: boolean;
  onQuoteClick: (index: number) => void;
}

export default function CriterionCard({ result, flashing, onQuoteClick }: Props) {
  const { feedback } = result;
  const lostPoints = result.median_points < result.max_points;
  const hasRange = result.min_points !== result.max_points_scored;
  // Feedback refers to verified passages by 1-based position among the verified ones.
  const verified = result.evidence.map((e, index) => ({ e, index })).filter((x) => x.e.verified);

  return (
    <article
      id={`criterion-${result.criterion_id}`}
      aria-label={result.name}
      className={`scroll-mt-4 rounded-lg border bg-white p-4 shadow-sm transition-shadow ${flashing ? "border-indigo-400 ring-2 ring-indigo-300" : "border-slate-200"}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-lg font-semibold">{result.name}</h3>
          {result.chosen_level && <p className="text-sm text-slate-600">Closest level: {result.chosen_level}</p>}
        </div>
        <div className="text-right">
          <p className="text-xl font-bold">
            {fmt(result.median_points)}
            <span className="text-base font-normal text-slate-500"> / {fmt(result.max_points)}</span>
          </p>
          {hasRange && (
            <p className="text-xs text-slate-500">
              range {fmt(result.min_points)}&ndash;{fmt(result.max_points_scored)}
            </p>
          )}
        </div>
      </header>

      <div className="mt-2 flex flex-wrap gap-2">
        {result.uncertain && <Badge tone="amber">Uncertain: grading runs disagreed</Badge>}
        {result.confidence && <Badge tone="slate">{result.confidence} confidence</Badge>}
        {!lostPoints && <Badge tone="green">Full marks</Badge>}
      </div>

      <section className="mt-4">
        <h4 className="text-sm font-semibold text-slate-800">Why this score</h4>
        <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{result.reasoning}</p>
      </section>

      {result.evidence.length > 0 && (
        <section className="mt-4">
          <h4 className="text-sm font-semibold text-slate-800">Evidence from your draft</h4>
          <ul className="mt-1 space-y-2">
            {result.evidence.map((item, index) => (
              <li key={index} className="text-sm">
                {item.verified ? (
                  <button
                    type="button"
                    onClick={() => onQuoteClick(index)}
                    className={`w-full rounded border-l-4 px-3 py-1.5 text-left hover:bg-slate-50 ${item.supports === "met" ? "border-green-500" : "border-red-500"}`}
                  >
                    <span className="sr-only">{item.supports === "met" ? "Meets criterion: " : "Falls short: "}</span>
                    &ldquo;{item.quote}&rdquo;
                    <span className="ml-2 text-xs text-indigo-700">Show in draft</span>
                  </button>
                ) : (
                  <div className="rounded border-l-4 border-slate-300 bg-slate-50 px-3 py-1.5 text-slate-600">
                    <Badge tone="slate">couldn&apos;t be located in your draft</Badge>
                    <p className="mt-1 italic">&ldquo;{item.quote}&rdquo;</p>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {feedback && (
        <section className="mt-4 rounded-md bg-indigo-50 p-3">
          <h4 className="text-sm font-semibold text-indigo-900">How to improve</h4>
          <p className="mt-1 text-sm text-indigo-950">{feedback.whats_missing}</p>
          {feedback.where_in_draft && <p className="mt-2 text-sm text-indigo-900"><strong>Where:</strong> {feedback.where_in_draft}</p>}
          {feedback.evidence_indexes.length > 0 && (
            <p className="mt-1 text-sm">
              {feedback.evidence_indexes
                .filter((n) => verified[n - 1])
                .map((n) => (
                  <button key={n} type="button" className="mr-3 text-indigo-700 underline" onClick={() => onQuoteClick(verified[n - 1].index)}>
                    See passage {n}
                  </button>
                ))}
            </p>
          )}
          <p className="mt-3 text-sm font-medium text-indigo-900">Questions to think about</p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-indigo-950">
            {feedback.guiding_questions.map((q) => <li key={q}>{q}</li>)}
          </ul>
          {feedback.is_fallback && (
            <p className="mt-2 text-xs text-indigo-800">General guidance from the rubric: personalised feedback wasn&apos;t available for this criterion.</p>
          )}
        </section>
      )}
    </article>
  );
}
