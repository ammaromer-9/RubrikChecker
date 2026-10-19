import type {
  Assignment,
  Comparison,
  Grading,
  History,
  NewAssignment,
  ProjectSummary,
  Rubric,
  Strictness,
  Submission,
  User,
} from "./types";

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

/** Fired when a signed-in request comes back 401, so the app can send the user to the sign-in page. */
export const SESSION_EXPIRED_EVENT = "rubriccheck:session-expired";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/api${path}`, {
      ...init,
      // The session cookie. Same-origin requests send it by default; a separate API origin needs "include".
      credentials: API_BASE ? "include" : "same-origin",
    });
  } catch {
    throw new ApiError(0, "Could not reach the server. Is the backend running?");
  }
  if (!response.ok) {
    // Signing in or checking who you are legitimately returns 401; anything else means the session ended.
    if (response.status === 401 && !path.startsWith("/auth/")) {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    throw new ApiError(response.status, await readError(response));
  }
  if (response.status === 204) return undefined as T;
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
  register: (body: { email: string; password: string; display_name?: string }) =>
    request<User>("/auth/register", json("POST", body)),
  login: (body: { email: string; password: string }) => request<User>("/auth/login", json("POST", body)),
  logout: () => request<void>("/auth/logout", json("POST")),
  me: () => request<User>("/auth/me"),

  listProjects: () => request<ProjectSummary[]>("/assignments"),
  renameProject: (id: number, title: string) => request<Assignment>(`/assignments/${id}`, json("PATCH", { title })),
  deleteProject: (id: number) => request<void>(`/assignments/${id}`, { method: "DELETE" }),

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
  setStrictness: (id: number, teacherStrictness: Strictness) =>
    request<Assignment>(`/assignments/${id}/strictness`, json("PUT", { teacher_strictness: teacherStrictness })),
  /** Grades the draft. `strictness` overrides the assignment's setting for this grading only. */
  gradeSubmission: (submissionId: number, strictness?: Strictness) =>
    request<Grading>(
      `/submissions/${submissionId}/grade`,
      json("POST", strictness ? { teacher_strictness: strictness } : undefined),
    ),
  getGrading: (id: number) => request<Grading>(`/gradings/${id}`),

  getHistory: (assignmentId: number) => request<History>(`/assignments/${assignmentId}/history`),
  compare: (submissionId: number, previousId: number) =>
    request<Comparison>(`/submissions/${submissionId}/compare/${previousId}`),
};
