import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Rubric } from "../api/types";
import RubricEditor, { validateRubric } from "./RubricEditor";

const rubric: Rubric = {
  criteria: [
    {
      id: "thesis", name: "Thesis", max_points: 10,
      levels: [
        { label: "Excellent", points: 10, description: "Clear", inferred: false },
        { label: "Fair", points: 5, description: "Suggested by AI", inferred: true },
      ],
    },
  ],
};

describe("validateRubric", () => {
  it("accepts a good rubric", () => expect(validateRubric(rubric)).toEqual([]));

  it("catches the same problems the backend rejects", () => {
    const bad: Rubric = {
      criteria: [
        { id: "a", name: "A", max_points: 5, levels: [
          { label: "Top", points: 9, description: "", inferred: false },
          { label: "top", points: 1, description: "", inferred: false },
        ] },
        { id: "a", name: "", max_points: 0, levels: [] },
      ],
    };
    const text = validateRubric(bad).join(" | ");
    expect(text).toMatch(/worth more than/);
    expect(text).toMatch(/labels must be different/);
    expect(text).toMatch(/duplicate criterion id/);
    expect(text).toMatch(/needs a name/);
    expect(text).toMatch(/max points must be greater than 0/);
    expect(text).toMatch(/at least one level/);
    expect(validateRubric({ criteria: [] })).toContain("Add at least one criterion.");
  });
});

describe("RubricEditor", () => {
  const setup = (onConfirm = vi.fn()) => {
    render(<RubricEditor initial={rubric} confirmed={false} saving={false} serverError={null} onConfirm={onConfirm} />);
    return onConfirm;
  };

  it("flags inferred levels and clears the flag when the level is edited", async () => {
    setup();
    expect(screen.getByText("inferred", { selector: "span" })).toBeInTheDocument();
    expect(screen.getByText(/Some levels were/)).toBeInTheDocument();
    await userEvent.type(screen.getAllByLabelText("Level description")[1], "!");
    expect(screen.queryByText("inferred", { selector: "span" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Some levels were/)).not.toBeInTheDocument();
  });

  it("confirms the edited rubric", async () => {
    const onConfirm = setup();
    const name = screen.getByLabelText("Criterion name");
    await userEvent.clear(name);
    await userEvent.type(name, "Argument");
    await userEvent.click(screen.getByRole("button", { name: "Confirm rubric" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm.mock.calls[0][0].criteria[0].name).toBe("Argument");
  });

  it("blocks confirming while the rubric is invalid and says why", async () => {
    const onConfirm = setup();
    const points = within(screen.getByRole("region", { name: "Criterion Thesis" })).getAllByLabelText("Level points")[0];
    await userEvent.clear(points);
    await userEvent.type(points, "99");
    expect(screen.getByRole("button", { name: "Confirm rubric" })).toBeDisabled();
    expect(within(screen.getByLabelText("Rubric problems")).getByText(/worth more than/)).toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("adds and removes levels", async () => {
    setup();
    await userEvent.click(screen.getByRole("button", { name: "Add level" }));
    expect(screen.getAllByLabelText("Level label")).toHaveLength(3);
    await userEvent.click(screen.getAllByRole("button", { name: "Remove" })[2]);
    expect(screen.getAllByLabelText("Level label")).toHaveLength(2);
  });
});
