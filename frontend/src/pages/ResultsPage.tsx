import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { api } from "../api/client";
import ResultsView from "../components/ResultsView";
import { ErrorBanner, LoadingPanel, PageHeader } from "../components/ui";

export default function ResultsPage() {
  const id = Number(useParams().id);
  const grading = useQuery({ queryKey: ["grading", id], queryFn: () => api.getGrading(id) });

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
  return (
    <>
      <PageHeader title="Your results" />
      <ResultsView grading={grading.data} />
    </>
  );
}
