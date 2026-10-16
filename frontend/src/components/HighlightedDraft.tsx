import { forwardRef } from "react";

import type { CriterionResult } from "../api/types";
import { buildSegments, quoteKey, type QuoteRef } from "../lib/highlight";

interface Props {
  draft: string;
  criteria: CriterionResult[];
  /** Key of the quote to emphasize briefly, e.g. "thesis:0". */
  flashQuote: string | null;
  onQuoteClick: (ref: QuoteRef) => void;
}

const HighlightedDraft = forwardRef<HTMLDivElement, Props>(function HighlightedDraft(
  { draft, criteria, flashQuote, onQuoteClick },
  ref,
) {
  const segments = buildSegments(draft, criteria);
  return (
    <div ref={ref} className="whitespace-pre-wrap break-words text-[15px] leading-7 text-slate-900" data-testid="draft">
      {segments.map((segment, i) => {
        if (segment.refs.length === 0) return <span key={i}>{segment.text}</span>;
        const first = segment.refs[0];
        const tone = first.supports === "met" ? "bg-green-200 decoration-green-600" : "bg-red-200 decoration-red-600";
        const flashing = segment.refs.some((r) => quoteKey(r.criterionId, r.index) === flashQuote);
        return (
          <mark
            key={i}
            role="button"
            tabIndex={0}
            data-quotes={segment.refs.map((r) => quoteKey(r.criterionId, r.index)).join(" ")}
            data-supports={first.supports}
            title={`${first.supports === "met" ? "Meets" : "Falls short of"} the criterion – click to see why`}
            className={`cursor-pointer rounded-sm px-0.5 text-slate-900 underline decoration-1 underline-offset-2 ${tone} ${flashing ? "ring-2 ring-indigo-500" : ""}`}
            onClick={() => onQuoteClick(first)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onQuoteClick(first);
              }
            }}
          >
            {segment.text}
          </mark>
        );
      })}
    </div>
  );
});

export default HighlightedDraft;
