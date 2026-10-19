import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import StrictnessPicker from "./StrictnessPicker";

describe("StrictnessPicker", () => {
  it("offers lenient, standard and strict, with the current one selected", () => {
    render(<StrictnessPicker value="standard" onChange={() => {}} />);
    expect(screen.getByRole("group", { name: /How tough is your teacher/ })).toBeInTheDocument();
    expect(screen.getAllByRole("radio").map((r) => (r as HTMLInputElement).value)).toEqual(["lenient", "standard", "strict"]);
    expect(screen.getByRole("radio", { name: /Standard/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Strict/ })).not.toBeChecked();
  });

  it("reports the choice", async () => {
    const onChange = vi.fn();
    render(<StrictnessPicker value="standard" onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: /Lenient/ }));
    expect(onChange).toHaveBeenCalledWith("lenient");
  });

  it("can be disabled while a grading runs", async () => {
    const onChange = vi.fn();
    render(<StrictnessPicker value="strict" onChange={onChange} disabled />);
    expect(screen.getByRole("radio", { name: /Lenient/ })).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: /Lenient/ }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("is honest that it only nudges borderline calls and cannot change the rubric", () => {
    render(<StrictnessPicker value="standard" onChange={() => {}} />);
    expect(screen.getByText(/only nudges borderline calls/)).toBeInTheDocument();
    expect(screen.getByText(/can.t change your rubric/)).toBeInTheDocument();
  });
});
