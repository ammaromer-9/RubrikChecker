import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import FileOrTextInput from "../components/FileOrTextInput";
import { Button, ErrorBanner, LoadingPanel, PageHeader, Spinner } from "../components/ui";

// Matches the backend's default MAX_DRAFT_CHARS; the server enforces the real limit.
const DRAFT_LIMIT = 50_000;

export default function SubmitDraftPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const [draft, setDraft] = useState("");
  // Kept so a failed grading can be retried without saving the same draft twice.
  const [submissionId, setSubmissionId] = useState<number | null>(null);

  const assignment = useQuery({ queryKey: ["assignment", id], queryFn: () => api.getAssignment(id) });

  const check = useMutation({
    mutationFn: async () => {
      let sid = submissionId;
      if (sid === null) {
        sid = (await api.createSubmission(id, draft)).id;
        setSubmissionId(sid);
      }
      return api.gradeSubmission(sid);
    },
    onSuccess: (grading) => navigate(`/gradings/${grading.id}`),
  });

  if (assignment.isPending) return <LoadingPanel title="Loading assignment…" />;
  if (assignment.isError) return <ErrorBanner message={assignment.error.message} />;

  if (!assignment.data.rubric_confirmed) {
    return (
      <>
        <PageHeader title="Confirm the rubric first" />
        <p className="text-slate-700">
          Grading only uses a rubric you&apos;ve reviewed and confirmed.{" "}
          <Link className="text-indigo-700 underline" to={`/assignments/${id}/rubric`}>Go to rubric review</Link>
        </p>
      </>
    );
  }

  const tooLong = draft.length > DRAFT_LIMIT;
  const busy = check.isPending;

  return (
    <>
      <PageHeader
        title="Submit your draft"
        subtitle={`${assignment.data.title}: paste or upload your draft. We'll predict a score and show you where to improve. We never rewrite your work.`}
      />
      <form
        className="space-y-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim() && !tooLong) check.mutate();
        }}
      >
        <FileOrTextInput
          label="Your draft"
          value={draft}
          onChange={(text) => {
            setDraft(text);
            setSubmissionId(null); // edited text is a different draft
          }}
          rows={16}
          maxChars={DRAFT_LIMIT}
          placeholder="Paste your draft here."
        />
        {busy && (
          <LoadingPanel title="Grading your draft…">
            Each rubric criterion is graded several times to measure how consistent the score is. This can take a minute or two. Keep this tab open.
          </LoadingPanel>
        )}
        <ErrorBanner message={check.error?.message} />
        <Button type="submit" disabled={!draft.trim() || tooLong || busy}>
          {busy && <Spinner className="h-4 w-4" />}
          {check.isError && submissionId !== null ? "Try grading again" : "Check my draft"}
        </Button>
      </form>
    </>
  );
}
