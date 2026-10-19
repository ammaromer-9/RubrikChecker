import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { history } from "../test/fixtures";
import HistoryView from "./HistoryView";
import ScoreTrend from "./ScoreTrend";

const renderHistory = (h = history) =>
  render(
    <MemoryRouter>
      <HistoryView history={h} />
    </MemoryRouter>,
  );

describe("HistoryView", () => {
  it("summarises the trend across graded versions", () => {
    renderHistory();
    expect(screen.getByTestId("trend-summary")).toHaveTextContent("8 → 13 out of 16 across 2 versions (+5)");
  });

  it("draws one trend point per graded version and describes the chart for screen readers", () => {
    renderHistory();
    expect(screen.getAllByTestId("trend-point")).toHaveLength(2);
    expect(screen.getByRole("img")).toHaveAccessibleName(/v1: 8 of 16, v2: 13 of 16/);
  });

  it("shows each version's scores with the change since the previous graded version", () => {
    renderHistory();
    expect(screen.getByTestId("overall-v1")).toHaveTextContent("8/16, likely 5–9");
    expect(screen.getByTestId("overall-v2")).toHaveTextContent("13/16, likely 12–14");
    expect(screen.getByTestId("overall-v2")).toHaveTextContent("+5");
    expect(screen.getByTestId("thesis-v2")).toHaveTextContent("10 / 10");
    expect(screen.getByTestId("thesis-v2")).toHaveTextContent("+5");
    expect(screen.getByTestId("support-v2")).toHaveTextContent("(0)");
  });

  it("flags criteria whose runs disagreed", () => {
    renderHistory();
    expect(within(screen.getByTestId("support-v1")).getByTitle("Grading runs disagreed")).toBeInTheDocument();
    expect(within(screen.getByTestId("support-v2")).queryByTitle("Grading runs disagreed")).not.toBeInTheDocument();
  });

  it("marks ungraded versions and does not offer a comparison for them", () => {
    renderHistory();
    expect(screen.getByTestId("overall-v3")).toHaveTextContent("Not graded");
    expect(screen.getByTestId("thesis-v3")).toHaveTextContent("–");
    expect(screen.getAllByRole("link", { name: /Compare with/ })).toHaveLength(1);
  });

  it("links versions to their results and consecutive graded versions to a comparison", () => {
    renderHistory();
    expect(screen.getByRole("link", { name: "V1" })).toHaveAttribute("href", "/gradings/7");
    expect(screen.getByRole("link", { name: "V2" })).toHaveAttribute("href", "/gradings/8");
    expect(screen.getByRole("link", { name: "Compare with V1" })).toHaveAttribute("href", "/submissions/4/compare/3");
    expect(screen.getByRole("link", { name: "Submit a new version" })).toHaveAttribute("href", "/assignments/2/submit");
  });

  it("labels the teacher strictness each version was graded with", () => {
    renderHistory();
    expect(screen.getByTestId("strictness-v1")).toHaveTextContent("Standard teacher");
    expect(screen.getByTestId("strictness-v2")).toHaveTextContent("Strict teacher");
    expect(screen.queryByTestId("strictness-v3")).not.toBeInTheDocument(); // never graded
  });

  it("invites a second version when only one has been graded", () => {
    renderHistory({ ...history, versions: [history.versions[0]] });
    expect(screen.getByText(/Submit another version/)).toBeInTheDocument();
    expect(screen.queryByTestId("trend-summary")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Compare with/ })).not.toBeInTheDocument();
  });

  it("handles an assignment with nothing graded", () => {
    renderHistory({ ...history, versions: [{ ...history.versions[2] }] });
    expect(screen.getByText("No version has been graded yet.")).toBeInTheDocument();
  });
});

describe("ScoreTrend", () => {
  it("renders nothing without points", () => {
    const { container } = render(<ScoreTrend points={[]} maxPossible={10} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("clamps values outside the scale instead of drawing off-chart", () => {
    render(<ScoreTrend points={[{ label: "v1", median: 99, min: 99, max: 99 }]} maxPossible={10} />);
    const circle = screen.getByTestId("trend-point").querySelector("circle")!;
    expect(Number(circle.getAttribute("cy"))).toBeGreaterThanOrEqual(0);
  });
});
