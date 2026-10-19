import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { ProjectSummary } from "../api/types";
import { Badge, ErrorBanner, LoadingPanel, PageHeader } from "../components/ui";
import { fmt, fmtDelta } from "../lib/format";
import { strictnessLabel } from "../lib/strictness";

function Score({ project }: { project: ProjectSummary }) {
  const latest = project.latest;
  if (!latest) {
    return <p className="text-sm text-slate-500">{project.attempts === 0 ? "No attempts yet" : "Not graded yet"}</p>;
  }
  return (
    <div>
      <p className="text-2xl font-bold" data-testid={`score-${project.id}`}>
        {fmt(latest.median)}
        <span className="text-base font-normal text-slate-500"> / {fmt(latest.max_possible)}</span>
      </p>
      <p className="text-xs text-slate-500">
        attempt {latest.version_number}, likely {fmt(latest.min)}&ndash;{fmt(latest.max)}
        {latest.change !== null && (
          <span
            data-testid={`change-${project.id}`}
            className={`ml-2 font-medium ${latest.change > 0 ? "text-green-700" : latest.change < 0 ? "text-red-700" : "text-slate-500"}`}
          >
            <span aria-hidden="true">{latest.change > 0 ? "▲" : latest.change < 0 ? "▼" : "–"}</span>{" "}
            {fmtDelta(latest.change)} since the attempt before
          </span>
        )}
      </p>
    </div>
  );
}

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.listProjects });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteProject(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
  });

  function confirmDelete(project: ProjectSummary) {
    const attempts = project.attempts === 1 ? "its 1 attempt" : `all ${project.attempts} attempts`;
    if (window.confirm(`Delete "${project.title}" and ${attempts}? This can't be undone.`)) remove.mutate(project.id);
  }

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <PageHeader title="Your projects" subtitle="One project per assignment. Each keeps every attempt and its scores." />
        <Link className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700" to="/projects/new">
          New project
        </Link>
      </div>

      <ErrorBanner message={remove.error?.message} />
      {projects.isPending && <LoadingPanel title="Loading your projects…" />}
      {projects.isError && <ErrorBanner message={projects.error.message} />}

      {projects.data?.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
          <h2 className="text-lg font-semibold">Start your first project</h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-600">
            Add an assignment and its rubric, then check your drafts against it. Every attempt is saved here.
          </p>
          <Link className="mt-4 inline-block rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700" to="/projects/new">
            Create a project
          </Link>
        </div>
      )}

      <ul className="grid gap-4 md:grid-cols-2">
        {projects.data?.map((project) => (
          <li key={project.id} className="flex flex-col justify-between rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
            <div>
              <div className="flex items-start justify-between gap-3">
                <h2 className="min-w-0 break-words text-lg font-semibold">
                  <Link className="hover:text-indigo-700 hover:underline" to={`/projects/${project.id}`}>
                    {project.title}
                  </Link>
                </h2>
                {!project.rubric_confirmed && <Badge tone="amber">Setup unfinished</Badge>}
              </div>
              <p className="mt-1 text-xs text-slate-500">
                Created {new Date(project.created_at).toLocaleDateString()} &middot; {project.attempts}{" "}
                {project.attempts === 1 ? "attempt" : "attempts"} &middot; {strictnessLabel(project.teacher_strictness)} teacher
              </p>
              <div className="mt-4"><Score project={project} /></div>
            </div>
            <div className="mt-5 flex flex-wrap items-center gap-3 text-sm">
              {project.rubric_confirmed ? (
                <Link className="font-medium text-indigo-700 underline" to={`/projects/${project.id}/submit`}>New attempt</Link>
              ) : (
                <Link className="font-medium text-indigo-700 underline" to={`/projects/${project.id}/rubric`}>Finish setup</Link>
              )}
              <Link className="text-indigo-700 underline" to={`/projects/${project.id}`}>Open</Link>
              <button
                type="button"
                onClick={() => confirmDelete(project)}
                disabled={remove.isPending}
                className="ml-auto text-red-700 hover:underline disabled:text-slate-400"
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
