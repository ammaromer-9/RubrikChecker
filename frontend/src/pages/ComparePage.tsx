import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { api } from "../api/client";
import ComparisonView from "../components/ComparisonView";
import { ErrorBanner, LoadingPanel, PageHeader } from "../components/ui";

export default function ComparePage() {
  const params = useParams();
  const id = Number(params.id);
  const previousId = Number(params.previousId);
  const comparison = useQuery({
    queryKey: ["compare", id, previousId],
    queryFn: () => api.compare(id, previousId),
  });

  if (comparison.isPending) return <LoadingPanel title="Comparing versions…" />;
  if (comparison.isError) return <ErrorBanner message={comparison.error.message} />;
  return (
    <>
      <PageHeader title="What changed" subtitle="How your newer draft compares with the earlier one." />
      <ComparisonView comparison={comparison.data} />
    </>
  );
}
