import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "../api/client";
import type { ProjectSummary } from "../api/types";
import { assignment, history } from "../test/fixtures";
import { mockSystemTheme, renderApp } from "../test/render";

const project = (overrides: Partial<ProjectSummary> = {}): ProjectSummary => ({
  id: 1,
  title: "English essay",
  created_at: "2026-10-01T10:00:00Z",
  rubric_confirmed: true,
  teacher_strictness: "standard",
  attempts: 3,
  graded_attempts: 2,
  latest: { version_number: 2, median: 13, min: 12, max: 14, max_possible: 16, change: 5 },
  ...overrides,
});

beforeEach(() => mockSystemTheme(false));
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("the projects list", () => {
  it("invites you to start a first project when there are none", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([]);
    renderApp("/projects");
    expect(await screen.findByRole("heading", { name: "Start your first project" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create a project" })).toHaveAttribute("href", "/projects/new");
    expect(screen.getByRole("link", { name: "New project" })).toHaveAttribute("href", "/projects/new");
  });

  it("shows each project's name, attempts and latest score with the change", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([
      project(),
      project({ id: 2, title: "History report", attempts: 1, graded_attempts: 1, teacher_strictness: "strict",
        latest: { version_number: 1, median: 20, min: 18, max: 21, max_possible: 30, change: null } }),
    ]);
    renderApp("/projects");
    expect(await screen.findByRole("link", { name: "English essay" })).toHaveAttribute("href", "/projects/1");
    expect(screen.getByRole("link", { name: "History report" })).toHaveAttribute("href", "/projects/2");

    expect(screen.getByTestId("score-1")).toHaveTextContent("13 / 16");
    expect(screen.getByTestId("change-1")).toHaveTextContent("+5 since the attempt before");
    expect(screen.getByTestId("change-1")).toHaveClass("text-green-700");
    expect(screen.getByText(/3 attempts/)).toBeInTheDocument();

    expect(screen.getByTestId("score-2")).toHaveTextContent("20 / 30");
    expect(screen.queryByTestId("change-2")).not.toBeInTheDocument(); // only one graded attempt
    expect(screen.getByText(/1 attempt ·/)).toBeInTheDocument();
    expect(screen.getByText(/Strict teacher/)).toBeInTheDocument();
  });

  it("shows a drop in red", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([project({ latest: { version_number: 2, median: 9, min: 8, max: 10, max_possible: 16, change: -2.5 } })]);
    renderApp("/projects");
    const change = await screen.findByTestId("change-1");
    expect(change).toHaveTextContent("−2.5");
    expect(change).toHaveClass("text-red-700");
  });

  it("says when nothing has been graded yet", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([
      project({ id: 1, attempts: 0, graded_attempts: 0, latest: null }),
      project({ id: 2, title: "Draft only", attempts: 2, graded_attempts: 0, latest: null }),
    ]);
    renderApp("/projects");
    expect(await screen.findByText("No attempts yet")).toBeInTheDocument();
    expect(screen.getByText("Not graded yet")).toBeInTheDocument();
  });

  it("points to finishing setup when the rubric is not confirmed", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([project({ rubric_confirmed: false, attempts: 0, graded_attempts: 0, latest: null })]);
    renderApp("/projects");
    expect(await screen.findByText("Setup unfinished")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Finish setup" })).toHaveAttribute("href", "/projects/1/rubric");
    expect(screen.queryByRole("link", { name: "New attempt" })).not.toBeInTheDocument();
  });

  it("offers a new attempt once the rubric is confirmed", async () => {
    vi.spyOn(api, "listProjects").mockResolvedValue([project()]);
    renderApp("/projects");
    expect(await screen.findByRole("link", { name: "New attempt" })).toHaveAttribute("href", "/projects/1/submit");
  });

  it("shows why the list could not load", async () => {
    vi.spyOn(api, "listProjects").mockRejectedValue(new ApiError(0, "Could not reach the server. Is the backend running?"));
    renderApp("/projects");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not reach the server");
  });

  describe("deleting", () => {
    it("asks first, naming the project, and only deletes when you agree", async () => {
      vi.spyOn(api, "listProjects").mockResolvedValue([project()]);
      const deleteProject = vi.spyOn(api, "deleteProject").mockResolvedValue(undefined);
      const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
      renderApp("/projects");

      await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
      expect(confirm).toHaveBeenCalledWith('Delete "English essay" and all 3 attempts? This can\'t be undone.');
      expect(deleteProject).not.toHaveBeenCalled();

      confirm.mockReturnValue(true);
      await userEvent.click(screen.getByRole("button", { name: "Delete" }));
      await waitFor(() => expect(deleteProject).toHaveBeenCalledExactlyOnceWith(1));
    });

    it("refreshes the list afterwards", async () => {
      const list = vi.spyOn(api, "listProjects").mockResolvedValueOnce([project()]).mockResolvedValue([]);
      vi.spyOn(api, "deleteProject").mockResolvedValue(undefined);
      vi.spyOn(window, "confirm").mockReturnValue(true);
      renderApp("/projects");
      await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
      expect(await screen.findByRole("heading", { name: "Start your first project" })).toBeInTheDocument();
      expect(list).toHaveBeenCalledTimes(2);
    });

    it("says so when deleting fails", async () => {
      vi.spyOn(api, "listProjects").mockResolvedValue([project()]);
      vi.spyOn(api, "deleteProject").mockRejectedValue(new ApiError(404, "Project not found."));
      vi.spyOn(window, "confirm").mockReturnValue(true);
      renderApp("/projects");
      await userEvent.click(await screen.findByRole("button", { name: "Delete" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("Project not found.");
    });
  });
});

describe("a project page", () => {
  beforeEach(() => {
    vi.spyOn(api, "getAssignment").mockResolvedValue({ ...assignment, id: 2, title: "Persuasive essay", rubric_confirmed: true });
    vi.spyOn(api, "getHistory").mockResolvedValue(history);
    vi.spyOn(api, "listProjects").mockResolvedValue([]);
  });

  it("shows the name, the setup and every attempt's score", async () => {
    renderApp("/projects/2");
    expect(await screen.findByRole("heading", { name: "Persuasive essay" })).toBeInTheDocument();
    expect(screen.getAllByText(/Standard teacher/).length).toBeGreaterThan(0); // header and attempts table
    expect(screen.getByRole("link", { name: "Review rubric or change teacher type" })).toHaveAttribute("href", "/projects/2/rubric");
    expect(await screen.findByTestId("overall-v2")).toHaveTextContent("13/16, likely 12–14");
    expect(screen.getByRole("link", { name: "← All projects" })).toHaveAttribute("href", "/projects");
    expect(screen.getByRole("link", { name: "New attempt" })).toHaveAttribute("href", "/projects/2/submit");
    expect(screen.queryByText(/hasn't been confirmed/)).not.toBeInTheDocument();
  });

  it("warns when the rubric is not confirmed", async () => {
    vi.spyOn(api, "getAssignment").mockResolvedValue({ ...assignment, id: 2, rubric_confirmed: false });
    renderApp("/projects/2");
    expect(await screen.findByText(/rubric hasn't been confirmed yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the rubric" })).toHaveAttribute("href", "/projects/2/rubric");
  });

  it("can be renamed", async () => {
    const rename = vi.spyOn(api, "renameProject").mockResolvedValue({ ...assignment, id: 2, title: "Chapter 3 essay" });
    renderApp("/projects/2");
    await userEvent.click(await screen.findByRole("button", { name: "Rename" }));

    const input = screen.getByLabelText("Project name");
    expect(input).toHaveValue("Persuasive essay");
    await userEvent.clear(input);
    await userEvent.type(input, "  Chapter 3 essay  ");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(rename).toHaveBeenCalledExactlyOnceWith(2, "Chapter 3 essay"); // trimmed
    expect(await screen.findByRole("heading", { name: "Chapter 3 essay" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Project name")).not.toBeInTheDocument();
  });

  it("will not save an empty name", async () => {
    renderApp("/projects/2");
    await userEvent.click(await screen.findByRole("button", { name: "Rename" }));
    await userEvent.clear(screen.getByLabelText("Project name"));
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("does nothing when the name is unchanged, and Cancel keeps the old name", async () => {
    const rename = vi.spyOn(api, "renameProject");
    renderApp("/projects/2");
    await userEvent.click(await screen.findByRole("button", { name: "Rename" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(rename).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    await userEvent.type(screen.getByLabelText("Project name"), " changed");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("heading", { name: "Persuasive essay" })).toBeInTheDocument();
    expect(rename).not.toHaveBeenCalled();
  });

  it("shows a rename error and keeps the editor open", async () => {
    vi.spyOn(api, "renameProject").mockRejectedValue(new ApiError(422, "title: String should have at most 120 characters"));
    renderApp("/projects/2");
    await userEvent.click(await screen.findByRole("button", { name: "Rename" }));
    await userEvent.type(screen.getByLabelText("Project name"), "!");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at most 120");
    expect(screen.getByLabelText("Project name")).toBeInTheDocument();
  });

  it("deletes after confirmation and returns to the list", async () => {
    const remove = vi.spyOn(api, "deleteProject").mockResolvedValue(undefined);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderApp("/projects/2");
    await userEvent.click(await screen.findByRole("button", { name: "Delete this project" }));
    expect(confirm).toHaveBeenCalledWith('Delete "Persuasive essay" and all 3 attempts? This can\'t be undone.');
    expect(remove).toHaveBeenCalledExactlyOnceWith(2);
    expect(await screen.findByRole("heading", { name: "Your projects" })).toBeInTheDocument();
  });

  it("does not delete if you decline", async () => {
    const remove = vi.spyOn(api, "deleteProject");
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderApp("/projects/2");
    await userEvent.click(await screen.findByRole("button", { name: "Delete this project" }));
    expect(remove).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Persuasive essay" })).toBeInTheDocument();
  });

  it("shows a missing or private project as not found", async () => {
    vi.spyOn(api, "getAssignment").mockRejectedValue(new ApiError(404, "Project not found."));
    renderApp("/projects/999");
    expect(await screen.findByRole("alert")).toHaveTextContent("Project not found.");
  });
});

describe("starting a project", () => {
  it("asks for a project name", async () => {
    renderApp("/projects/new");
    expect(await screen.findByRole("heading", { name: "New project" })).toBeInTheDocument();
    expect(screen.getByLabelText("Project name")).toBeInTheDocument();
    expect(screen.queryByText("Assignment title")).not.toBeInTheDocument();
  });

  it("creates the project and goes to the rubric review", async () => {
    const create = vi.spyOn(api, "createAssignment").mockResolvedValue({ ...assignment, id: 9 });
    vi.spyOn(api, "getAssignment").mockResolvedValue({ ...assignment, id: 9, rubric_parsed: null });
    vi.spyOn(api, "parseRubric").mockResolvedValue({ ...assignment, id: 9 });
    renderApp("/projects/new");

    await userEvent.type(await screen.findByLabelText("Project name"), "Essay one");
    await userEvent.type(screen.getByLabelText("Assignment instructions"), "Write.");
    await userEvent.type(screen.getByLabelText("Grading rubric"), "Thesis 10");
    await userEvent.click(screen.getByRole("button", { name: "Continue to rubric review" }));

    expect(create).toHaveBeenCalledExactlyOnceWith({ title: "Essay one", instructions_text: "Write.", rubric_raw_text: "Thesis 10" });
    expect(await screen.findByRole("heading", { name: "Review the rubric" })).toBeInTheDocument();
    const page = within(screen.getByRole("main"));
    expect(page.getByRole("link", { name: "← All projects" })).toHaveAttribute("href", "/projects");
  });
});
