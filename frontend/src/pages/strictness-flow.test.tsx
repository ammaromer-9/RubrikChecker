import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import { assignment, grading, history } from "../test/fixtures";
import ResultsPage from "./ResultsPage";
import ReviewRubricPage from "./ReviewRubricPage";

function renderAt(path: string, routes: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>{routes}</Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => vi.restoreAllMocks());

describe("choosing the teacher strictness on the rubric review page", () => {
  const routes = (
    <>
      <Route path="/projects/:id/rubric" element={<ReviewRubricPage />} />
      <Route path="/projects/:id/submit" element={<p>submit page</p>} />
    </>
  );

  function mockApi(teacherStrictness: "lenient" | "standard" | "strict" = "standard") {
    const calls: string[] = [];
    vi.spyOn(api, "getAssignment").mockResolvedValue({ ...assignment, teacher_strictness: teacherStrictness });
    vi.spyOn(api, "setStrictness").mockImplementation(async () => {
      calls.push("setStrictness");
      return assignment;
    });
    vi.spyOn(api, "confirmRubric").mockImplementation(async () => {
      calls.push("confirmRubric");
      return { ...assignment, rubric_confirmed: true };
    });
    return calls;
  }

  it("starts from the saved setting", async () => {
    mockApi("lenient");
    renderAt("/projects/2/rubric", routes);
    expect(await screen.findByRole("radio", { name: /Lenient/ })).toBeChecked();
  });

  it("saves the new setting, then the rubric, then moves on", async () => {
    const calls = mockApi();
    renderAt("/projects/2/rubric", routes);
    await userEvent.click(await screen.findByRole("radio", { name: /Strict/ }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm rubric" }));

    expect(await screen.findByText("submit page")).toBeInTheDocument();
    expect(api.setStrictness).toHaveBeenCalledExactlyOnceWith(2, "strict");
    expect(calls).toEqual(["setStrictness", "confirmRubric"]);
  });

  it("does not touch the setting when it was not changed", async () => {
    mockApi();
    renderAt("/projects/2/rubric", routes);
    await userEvent.click(await screen.findByRole("button", { name: "Confirm rubric" }));
    await screen.findByText("submit page");
    expect(api.setStrictness).not.toHaveBeenCalled();
    expect(api.confirmRubric).toHaveBeenCalledTimes(1);
  });

  it("shows the error and does not confirm if saving the setting fails", async () => {
    mockApi();
    vi.spyOn(api, "setStrictness").mockRejectedValue(new Error("Could not reach the server."));
    renderAt("/projects/2/rubric", routes);
    await userEvent.click(await screen.findByRole("radio", { name: /Lenient/ }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm rubric" }));
    expect(await screen.findByText("Could not reach the server.")).toBeInTheDocument();
    expect(api.confirmRubric).not.toHaveBeenCalled();
    expect(screen.queryByText("submit page")).not.toBeInTheDocument();
  });
});

describe("re-grading from the results page", () => {
  const routes = <Route path="/gradings/:id" element={<ResultsPage />} />;

  it("grades the same draft again with the chosen strictness and opens the new grading", async () => {
    vi.spyOn(api, "getGrading").mockImplementation(async (id) =>
      id === 7 ? grading : { ...grading, id: 99, strictness: "strict" },
    );
    vi.spyOn(api, "getHistory").mockResolvedValue(history);
    const regrade = vi.spyOn(api, "gradeSubmission").mockResolvedValue({ ...grading, id: 99, strictness: "strict" });

    renderAt("/gradings/7", routes);
    expect(await screen.findByTestId("strictness-note")).toHaveTextContent("standard teacher");

    await userEvent.click(screen.getByRole("radio", { name: /Strict/ }));
    await userEvent.click(screen.getByRole("button", { name: /Grade this draft again as a strict teacher/ }));

    expect(regrade).toHaveBeenCalledExactlyOnceWith(grading.submission_id, "strict");
    await waitFor(() => expect(screen.getByTestId("strictness-note")).toHaveTextContent("strict teacher"));
    // The new grading starts from its own setting, not the previous page's choice.
    expect(screen.getByRole("radio", { name: /Strict/ })).toBeChecked();
  });

  it("shows why a re-grade failed and stays on the page", async () => {
    vi.spyOn(api, "getGrading").mockResolvedValue(grading);
    vi.spyOn(api, "getHistory").mockResolvedValue(history);
    vi.spyOn(api, "gradeSubmission").mockRejectedValue(new Error("The AI service is busy or unavailable."));

    renderAt("/gradings/7", routes);
    await userEvent.click(await screen.findByRole("button", { name: /Grade this draft again/ }));
    expect(await screen.findByText("The AI service is busy or unavailable.")).toBeInTheDocument();
    expect(screen.getByTestId("overall")).toBeInTheDocument();
  });
});
