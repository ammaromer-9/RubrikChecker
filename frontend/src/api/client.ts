import type { Assignment, Comparison, Grading, History, NewAssignment, Rubric, Submission } from "./types";

// In development Vite proxies /api to the backend. In production, set VITE_API_BASE_URL at
// build time if the API is on a different origin (leave it empty to use the same origin).
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI sends `detail` as a string, or as a list of validation problems. */
async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((d: { msg?: string; loc?: unknown[] }) =>
          d.loc ? `${d.loc.slice(1).join(".")}: ${d.msg}` : String(d.msg),
        )
        .join("; ");
    }
  } catch {
    // not JSON
  }
  return `Request failed (${response.status}).`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api${path}`, init);
  } catch {
    throw new ApiError(0, "Could not reach the server. Is the backend running?");
  }
  if (!response.ok) throw new ApiError(response.status, await readError(response));
  return (await response.json()) as T;
}

function json(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

export const api = {
  health: () => request<{ status: string; database: string }>("/health"),

  extractFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ filename: string; text: string; char_count: number }>("/files/extract", {
      method: "POST",
      body: form,
    });
  },

  createAssignment: (body: NewAssignment) => request<Assignment>("/assignments", json("POST", body)),
  getAssignment: (id: number) => request<Assignment>(`/assignments/${id}`),
  parseRubric: (id: number) => request<Assignment>(`/assignments/${id}/parse-rubric`, json("POST")),
  confirmRubric: (id: number, rubric: Rubric) =>
    request<Assignment>(`/assignments/${id}/rubric`, json("PUT", rubric)),

  createSubmission: (assignmentId: number, draftText: string) =>
    request<Submission>(`/assignments/${assignmentId}/submissions`, json("POST", { draft_text: draftText })),
  gradeSubmission: (submissionId: number) =>
    request<Grading>(`/submissions/${submissionId}/grade`, json("POST")),
  getGrading: (id: number) => request<Grading>(`/gradings/${id}`),

  getHistory: (assignmentId: number) => request<History>(`/assignments/${assignmentId}/history`),
  compare: (submissionId: number, previousId: number) =>
    request<Comparison>(`/submissions/${submissionId}/compare/${previousId}`),
};
