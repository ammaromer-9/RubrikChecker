import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { grading } from "../test/fixtures";
import ResultsView from "./ResultsView";

const scrollIntoView = vi.fn();

function renderResults(overrides = {}) {
  return render(
    <MemoryRouter>
      <ResultsView grading={{ ...grading, ...overrides }} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  scrollIntoView.mockReset();
  // jsdom does not implement scrolling.
  Element.prototype.scrollIntoView = scrollIntoView;
});

describe("ResultsView", () => {
  it("shows the overall predicted score with its range", () => {
    renderResults();
    expect(screen.getByTestId("overall")).toHaveTextContent("13/16, likely 5–16");
  });

  it("lists per-criterion scores, ranges and the uncertain badge", () => {
    renderResults();
    const thesis = screen.getByRole("article", { name: "Thesis" });
    expect(within(thesis).getByText("Full marks")).toBeInTheDocument();
    expect(within(thesis).queryByText(/Uncertain/)).not.toBeInTheDocument();
    expect(within(thesis).getByText(/range 5/)).toBeInTheDocument();

    const support = screen.getByRole("article", { name: "Evidence & Support" });
    expect(within(support).getByText(/Uncertain: grading runs disagreed/)).toBeInTheDocument();
    expect(within(support).getByText(/range 0/)).toBeInTheDocument();
  });

  it("shows feedback and guiding questions only for criteria that lost points", () => {
    renderResults();
    const support = screen.getByRole("article", { name: "Evidence & Support" });
    expect(within(support).getByText("The evidence is general rather than specific.")).toBeInTheDocument();
    expect(within(support).getByText("What specific study could you point to?")).toBeInTheDocument();
    const thesis = screen.getByRole("article", { name: "Thesis" });
    expect(within(thesis).queryByText("How to improve")).not.toBeInTheDocument();
  });

  it("renders the instruction checklist with pass and fail states", () => {
    renderResults();
    const list = screen.getByRole("region", { name: "Instruction checks" });
    expect(within(list).getByText(/At least 50 words/)).toBeInTheDocument();
    expect(within(list).getByText(/not met/)).toBeInTheDocument();
    expect(within(list).getByText(/\(met\)/)).toBeInTheDocument();
    expect(within(list).getByText(/28 words short/)).toBeInTheDocument();
  });

  it("shows the top fixes summary", () => {
    renderResults();
    const fixes = screen.getByRole("region", { name: "Top fixes" });
    expect(within(fixes).getByText("Top 1 things to fix first")).toBeInTheDocument();
    expect(within(fixes).getByText("3 pts at stake")).toBeInTheDocument();
  });

  it("highlights verified quotes green (met) and red (not met), and skips unverified ones", () => {
    renderResults();
    const marks = within(screen.getByTestId("draft")).getAllByRole("button");
    expect(marks.map((m) => [m.textContent, m.getAttribute("data-supports")])).toEqual([
      ["Social media harms teen sleep.", "met"],
      ["Many students scroll late at night.", "not_met"],
      ["schools should not ban phones outright", "not_met"],
    ]);
    expect(marks[0]).toHaveClass("bg-green-200");
    expect(marks[1]).toHaveClass("bg-red-200");
    expect(within(screen.getByTestId("draft")).queryByText(/eight hours/)).not.toBeInTheDocument();
    expect(screen.getByText(/couldn.t be located in your draft/)).toBeInTheDocument();
  });

  it("clicking a highlighted quote scrolls to its criterion card", async () => {
    renderResults();
    await userEvent.click(within(screen.getByTestId("draft")).getByText("Many students scroll late at night."));
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    expect(scrollIntoView.mock.contexts[0]).toBe(document.getElementById("criterion-support"));
  });

  it("clicking evidence in a criterion card scrolls to the highlight in the draft", async () => {
    renderResults();
    const support = screen.getByRole("article", { name: "Evidence & Support" });
    await userEvent.click(within(support).getAllByRole("button", { name: /Show in draft/ })[0]);
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    const target = scrollIntoView.mock.contexts[0] as HTMLElement;
    expect(target.textContent).toBe("Many students scroll late at night.");
    expect(target.getAttribute("data-quotes")).toContain("support:0");
  });

  it("feedback passage links point at the right highlighted text", async () => {
    renderResults();
    const support = screen.getByRole("article", { name: "Evidence & Support" });
    await userEvent.click(within(support).getByRole("button", { name: "See passage 2" }));
    expect((scrollIntoView.mock.contexts[0] as HTMLElement).textContent).toBe("schools should not ban phones outright");
  });

  it("clicking a top fix scrolls to that criterion", async () => {
    renderResults();
    await userEvent.click(within(screen.getByRole("region", { name: "Top fixes" })).getByRole("button", { name: "Evidence & Support" }));
    expect(scrollIntoView.mock.contexts[0]).toBe(document.getElementById("criterion-support"));
  });

  it("explains when generic fallback feedback is shown", () => {
    const fallback = { ...grading.criteria[1], feedback: { ...grading.criteria[1].feedback!, is_fallback: true } };
    renderResults({ criteria: [grading.criteria[0], fallback] });
    expect(screen.getByText(/General guidance from the rubric/)).toBeInTheDocument();
  });

  it("omits the range for a single run", () => {
    renderResults({ overall: { median: 13, min: 13, max: 13, max_possible: 16 }, num_runs: 1 });
    expect(screen.getByTestId("overall")).toHaveTextContent("13/16");
    expect(screen.getByTestId("overall")).not.toHaveTextContent("likely");
    expect(screen.getByText(/1 independent grading run per criterion/)).toBeInTheDocument();
  });
});
