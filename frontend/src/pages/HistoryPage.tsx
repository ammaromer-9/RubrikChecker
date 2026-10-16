import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { api } from "../api/client";
import HistoryView from "../components/HistoryView";
import { ErrorBanner, LoadingPanel, PageHeader } from "../components/ui";

export default function HistoryPage() {
  const id = Number(useParams().id);
  const history = useQuery({ queryKey: ["history", id], queryFn: () => api.getHistory(id) });

  if (history.isPending) return <LoadingPanel title="Loading revision history…" />;
  if (history.isError) return <ErrorBanner message={history.error.message} />;
  return (
    <>
      <PageHeader title="Revision history" subtitle={history.data.title} />
      <HistoryView history={history.data} />
    </>
  );
}
