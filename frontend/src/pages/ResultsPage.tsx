import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import type { Strictness } from "../api/types";
import ResultsView from "../components/ResultsView";
import { ErrorBanner, LoadingPanel, PageHeader } from "../components/ui";

export default function ResultsPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const grading = useQuery({ queryKey: ["grading", id], queryFn: () => api.getGrading(id) });
  const assignmentId = grading.data?.assignment_id;
  // A new grading of the same draft, e.g. with a different teacher strictness.
  const regrade = useMutation({
    mutationFn: (strictness: Strictness) => api.gradeSubmission(grading.data!.submission_id, strictness),
    onSuccess: (next) => {
      void queryClient.invalidateQueries({ queryKey: ["history"] });
      navigate(`/gradings/${next.id}`);
    },
  });
  // Only used to find the earlier graded version for the "what changed" link.
  const history = useQuery({
    queryKey: ["history", assignmentId],
    queryFn: () => api.getHistory(assignmentId!),
    enabled: assignmentId !== undefined,
  });

  if (grading.isPending) return <LoadingPanel title="Loading your results…" />;
  if (grading.isError) return <ErrorBanner message={grading.error.message} />;
  if (grading.data.status !== "complete") {
    return (
      <>
        <PageHeader title="Results" />
        <ErrorBanner message={grading.data.error ?? `Grading status: ${grading.data.status}.`} />
      </>
    );
  }
  const previous = history.data?.versions
    .filter((v) => v.grading && v.version_number < grading.data.version_number)
    .at(-1);
  return (
    <>
      <PageHeader title="Your results" />
      <ResultsView
        key={grading.data.id} // fresh state (e.g. the re-grade choice) for each grading
        grading={grading.data}
        previousSubmissionId={previous?.submission_id}
        previousVersionNumber={previous?.version_number}
        onRegrade={(strictness) => regrade.mutate(strictness)}
        regrading={regrade.isPending}
        regradeError={regrade.error?.message ?? null}
      />
    </>
  );
}
