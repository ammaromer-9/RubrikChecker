import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { comparison } from "../test/fixtures";
import ComparisonView from "./ComparisonView";

function renderComparison(overrides = {}) {
  return render(
    <MemoryRouter>
      <ComparisonView comparison={{ ...comparison, ...overrides }} />
    </MemoryRouter>,
  );
}

describe("ComparisonView", () => {
  it("shows the overall change between attempts", () => {
    renderComparison();
    const overall = screen.getByTestId("overall-change");
    expect(overall).toHaveTextContent("8 → 13");
    expect(overall).toHaveTextContent("(+5)");
    expect(screen.getByText(/Attempt 1 → attempt 2/)).toBeInTheDocument();
  });

  it("says the change is likely real when the score ranges do not overlap", () => {
    renderComparison();
    expect(screen.getByTestId("noise-note")).toHaveTextContent("likely real");
  });

  it("warns that the change may be noise when the ranges overlap", () => {
    renderComparison({ overall: { ...comparison.overall, ranges_overlap: true } });
    expect(screen.getByTestId("noise-note")).toHaveTextContent(/may just be normal variation/);
  });

  it("makes no claim when the score did not change", () => {
    renderComparison({ overall: { ...comparison.overall, change: 0, current_median: 8 } });
    expect(screen.queryByTestId("noise-note")).not.toBeInTheDocument();
    expect(screen.getByTestId("overall-change")).toHaveTextContent("(0)");
  });

  it("lists the issues that were fixed with the original problem", () => {
    renderComparison();
    const fixed = screen.getByRole("region", { name: "Resolved issues" });
    expect(within(fixed).getByText(/Thesis/)).toBeInTheDocument();
    expect(within(fixed).getByText("+5 pts")).toBeInTheDocument();
    expect(within(fixed).getByText("Was: The thesis is vague.")).toBeInTheDocument();
  });

  it("hides the fixed-issues section when nothing was resolved", () => {
    renderComparison({ resolved_issues: [] });
    expect(screen.queryByRole("region", { name: "Resolved issues" })).not.toBeInTheDocument();
  });

  it("shows per-criterion before/after scores with change direction and badges", () => {
    renderComparison();
    const rows = within(screen.getByRole("region", { name: "Changes by criterion" })).getAllByRole("row").slice(1);
    const text = (name: string) => rows.find((r) => within(r).queryByRole("rowheader", { name }))!;

    expect(text("Thesis")).toHaveTextContent("5 / 10");
    expect(text("Thesis")).toHaveTextContent("10 / 10");
    expect(text("Thesis")).toHaveTextContent("improved +5");
    expect(within(text("Thesis")).getByText("fixed")).toBeInTheDocument();

    expect(text("Evidence & Support")).toHaveTextContent("unchanged 0");
    expect(within(text("Evidence & Support")).getByText("uncertain")).toBeInTheDocument();

    expect(text("Style")).toHaveTextContent("declined −1");
    expect(within(text("Style")).getByText("within normal variation")).toBeInTheDocument();

    expect(text("Extra credit")).toHaveTextContent("new criterion");
    expect(screen.getByText(/1 improved, 1 unchanged, 1 declined/)).toBeInTheDocument();
  });

  it("shows requirement changes and what is still to fix", () => {
    renderComparison();
    const requirements = screen.getByRole("region", { name: "Requirement changes" });
    expect(within(requirements).getByText("Now met")).toBeInTheDocument();
    expect(within(requirements).getByText("No longer met")).toBeInTheDocument();
    expect(within(requirements).getByText("Missing section(s): Conclusion.")).toBeInTheDocument();

    const remaining = screen.getByRole("region", { name: "Still to fix" });
    expect(within(remaining).getByText("3 pts at stake")).toBeInTheDocument();
  });

  it("congratulates when nothing is left to fix", () => {
    renderComparison({ remaining_fixes: [] });
    expect(screen.getByText(/Nothing is costing points in attempt 2/)).toBeInTheDocument();
  });

  it("links to the full results and the history", () => {
    renderComparison();
    expect(screen.getByRole("link", { name: /Full results for attempt 2/ })).toHaveAttribute("href", "/gradings/8");
    expect(screen.getByRole("link", { name: "All attempts" })).toHaveAttribute("href", "/projects/2");
  });

  it("warns when the two attempts were graded for different teachers", () => {
    renderComparison({
      strictness_differs: true,
      previous: { ...comparison.previous, strictness: "standard" },
      current: { ...comparison.current, strictness: "strict" },
    });
    const warning = screen.getByTestId("strictness-warning");
    expect(warning).toHaveTextContent("attempt 1: standard, attempt 2: strict");
    expect(warning).toHaveTextContent(/part of this change may come from that setting/);
  });

  it("stays quiet when both used the same setting", () => {
    renderComparison();
    expect(screen.queryByTestId("strictness-warning")).not.toBeInTheDocument();
  });
});
