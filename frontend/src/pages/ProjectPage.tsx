import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import HistoryView from "../components/HistoryView";
import { Button, ErrorBanner, LoadingPanel } from "../components/ui";
import { strictnessLabel } from "../lib/strictness";

/** One project: its name, and every attempt with its scores. */
export default function ProjectPage() {
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const project = useQuery({ queryKey: ["assignment", id], queryFn: () => api.getAssignment(id) });
  const history = useQuery({ queryKey: ["history", id], queryFn: () => api.getHistory(id) });

  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState("");

  const rename = useMutation({
    mutationFn: (title: string) => api.renameProject(id, title),
    onSuccess: (updated) => {
      queryClient.setQueryData(["assignment", id], updated);
      void queryClient.invalidateQueries({ queryKey: ["history", id] });
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      setEditing(false);
    },
  });
  const remove = useMutation({
    mutationFn: () => api.deleteProject(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate("/projects", { replace: true });
    },
  });

  if (project.isPending) return <LoadingPanel title="Loading project…" />;
  if (project.isError) return <ErrorBanner message={project.error.message} />;
  const data = project.data;

  function startRename() {
    setDraftName(data.title);
    rename.reset();
    setEditing(true);
  }

  function saveName(event: FormEvent) {
    event.preventDefault();
    const title = draftName.trim();
    if (title && title !== data.title) rename.mutate(title);
    else setEditing(false);
  }

  function confirmDelete() {
    const count = history.data?.versions.length ?? 0;
    if (window.confirm(`Delete "${data.title}" and ${count === 1 ? "its 1 attempt" : `all ${count} attempts`}? This can't be undone.`)) {
      remove.mutate();
    }
  }

  return (
    <>
      <p className="mb-2 text-sm"><Link className="text-indigo-700 underline" to="/projects">&larr; All projects</Link></p>

      <header className="mb-6">
        {editing ? (
          <form onSubmit={saveName} className="flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor="project-name">Project name</label>
            <input
              id="project-name"
              autoFocus
              maxLength={120}
              value={draftName}
              onChange={(e) => setDraftName(e.target.value)}
              className="min-w-0 flex-1 rounded-md border border-slate-300 bg-white p-2 text-2xl font-bold text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <Button type="submit" disabled={rename.isPending || !draftName.trim()}>Save</Button>
            <Button variant="secondary" onClick={() => setEditing(false)}>Cancel</Button>
          </form>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="min-w-0 break-words text-2xl font-bold tracking-tight">{data.title}</h1>
            <button type="button" onClick={startRename} className="text-sm text-indigo-700 underline">Rename</button>
          </div>
        )}
        <ErrorBanner message={rename.error?.message} />
        <p className="mt-1 text-sm text-slate-600">
          {strictnessLabel(data.teacher_strictness)} teacher &middot;{" "}
          <Link className="text-indigo-700 underline" to={`/projects/${id}/rubric`}>
            {data.rubric_confirmed ? "Review rubric or change teacher type" : "Finish setting up the rubric"}
          </Link>
        </p>
      </header>

      {!data.rubric_confirmed && (
        <div className="mb-6 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          This project&apos;s rubric hasn&apos;t been confirmed yet, so drafts can&apos;t be graded.{" "}
          <Link className="font-medium underline" to={`/projects/${id}/rubric`}>Go to the rubric</Link>
        </div>
      )}

      {history.isPending && <LoadingPanel title="Loading attempts…" />}
      {history.isError && <ErrorBanner message={history.error.message} />}
      {history.data && <HistoryView history={history.data} />}

      <section className="mt-10 border-t border-slate-200 pt-6" aria-label="Danger zone">
        <ErrorBanner message={remove.error?.message} />
        <Button variant="danger" onClick={confirmDelete} disabled={remove.isPending}>Delete this project</Button>
      </section>
    </>
  );
}
