import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { Rubric } from "../api/types";
import RubricEditor from "../components/RubricEditor";
import { Button, ErrorBanner, LoadingPanel, PageHeader } from "../components/ui";

export default function ReviewRubricPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const autoParse = (useLocation().state as { autoParse?: boolean } | null)?.autoParse === true;

  const assignment = useQuery({ queryKey: ["assignment", id], queryFn: () => api.getAssignment(id) });

  const parse = useMutation({
    mutationFn: () => api.parseRubric(id),
    onSuccess: (data) => queryClient.setQueryData(["assignment", id], data),
  });
  const confirm = useMutation({
    mutationFn: (rubric: Rubric) => api.confirmRubric(id, rubric),
    onSuccess: (data) => {
      queryClient.setQueryData(["assignment", id], data);
      navigate(`/assignments/${id}/submit`);
    },
  });

  // Parse automatically right after creating the assignment, never on a plain page visit.
  const started = useRef(false);
  useEffect(() => {
    if (autoParse && assignment.data && !assignment.data.rubric_parsed && !started.current) {
      started.current = true;
      parse.mutate();
    }
  }, [autoParse, assignment.data, parse]);

  if (assignment.isPending) return <LoadingPanel title="Loading assignment…" />;
  if (assignment.isError) return <ErrorBanner message={assignment.error.message} />;
  const data = assignment.data;

  return (
    <>
      <PageHeader
        title="Review the rubric"
        subtitle={`${data.title}: we turned your rubric into the table below. Fix anything that's wrong, then confirm. Grading only uses the confirmed version.`}
      />

      {parse.isPending && (
        <LoadingPanel title="Reading your rubric…">This usually takes 10 to 30 seconds.</LoadingPanel>
      )}
      <ErrorBanner message={parse.error?.message} />

      {data.rubric_parsed && !parse.isPending && (
        <div className="space-y-6">
          <RubricEditor
            key={JSON.stringify(data.rubric_parsed)}
            initial={data.rubric_parsed}
            confirmed={data.rubric_confirmed}
            saving={confirm.isPending}
            serverError={confirm.error?.message ?? null}
            onConfirm={(rubric) => confirm.mutate(rubric)}
          />
          <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <Button
              variant="secondary"
              disabled={parse.isPending}
              onClick={() => {
                if (window.confirm("Read the rubric again? Your edits so far will be replaced.")) parse.mutate();
              }}
            >
              Re-read the original rubric
            </Button>
          </div>
        </div>
      )}

      {!data.rubric_parsed && !parse.isPending && (
        <div className="space-y-3">
          <p className="text-slate-700">The rubric hasn&apos;t been read yet.</p>
          <Button onClick={() => parse.mutate()}>Read my rubric</Button>
        </div>
      )}

      <details className="mt-8 rounded-lg border border-slate-200 bg-white p-4 text-sm">
        <summary className="cursor-pointer font-medium">Original rubric text</summary>
        <pre className="mt-3 whitespace-pre-wrap text-slate-700">{data.rubric_raw_text}</pre>
      </details>
      <p className="mt-4 text-sm">
        <Link className="text-indigo-700 underline" to="/">Start over with a new assignment</Link>
      </p>
    </>
  );
}
