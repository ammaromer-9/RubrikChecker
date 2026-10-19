import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../api/client";
import FileOrTextInput from "./FileOrTextInput";

const CONTENTS = "Thesis (10 points): Excellent = a clear, arguable position stated early.";

/** Holds the value like a real page does, and exposes it so tests can check what the page would send. */
function Harness({ onValue = () => {} }: { onValue?: (v: string) => void }) {
  const [value, setValue] = useState("");
  onValue(value);
  return <FileOrTextInput label="Grading rubric" value={value} onChange={setValue} maxChars={100} />;
}

const pdf = () => new File(["%PDF-fake"], "rubric.pdf", { type: "application/pdf" });

function mockExtract(text = CONTENTS) {
  return vi.spyOn(api, "extractFile").mockResolvedValue({ filename: "rubric.pdf", text, char_count: text.length });
}

afterEach(() => vi.restoreAllMocks());

describe("FileOrTextInput", () => {
  it("lets you type or paste text as before", async () => {
    render(<Harness />);
    await userEvent.type(screen.getByLabelText("Grading rubric"), "typed text");
    expect(screen.getByLabelText("Grading rubric")).toHaveValue("typed text");
    expect(screen.getByText(/10 \/ 100 characters/)).toBeInTheDocument();
  });

  it("shows only the file name after an upload, never the file's contents", async () => {
    mockExtract();
    render(<Harness />);
    await userEvent.upload(screen.getByLabelText("Upload a file for Grading rubric"), pdf());

    expect(await screen.findByTestId("uploaded-file-name")).toHaveTextContent("rubric.pdf");
    expect(screen.queryByText(CONTENTS)).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument(); // no box showing the text
    expect(document.body).not.toHaveTextContent("clear, arguable position");
  });

  it("still passes the extracted text to the page so it is sent for grading", async () => {
    mockExtract();
    const seen = vi.fn();
    render(<Harness onValue={seen} />);
    await userEvent.upload(screen.getByLabelText("Upload a file for Grading rubric"), pdf());
    await screen.findByTestId("uploaded-file-name");
    expect(seen).toHaveBeenLastCalledWith(CONTENTS);
    expect(api.extractFile).toHaveBeenCalledTimes(1);
  });

  it("shows how much text was read, and warns in red when it is over the limit", async () => {
    mockExtract("x".repeat(150));
    render(<Harness />);
    await userEvent.upload(screen.getByLabelText("Upload a file for Grading rubric"), pdf());
    const count = await screen.findByText(/150 \/ 100 characters/);
    expect(count).toHaveClass("text-red-700");
  });

  it("removing the file clears the text and brings the box back", async () => {
    mockExtract();
    const seen = vi.fn();
    render(<Harness onValue={seen} />);
    await userEvent.upload(screen.getByLabelText("Upload a file for Grading rubric"), pdf());
    await userEvent.click(await screen.findByRole("button", { name: "Remove file" }));

    expect(seen).toHaveBeenLastCalledWith("");
    expect(screen.queryByTestId("uploaded-file-name")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Grading rubric")).toHaveValue("");
    expect(screen.getByRole("button", { name: "Upload PDF, Word or text file" })).toBeInTheDocument();
  });

  it("replacing the file swaps the name and the text", async () => {
    const extract = mockExtract();
    const seen = vi.fn();
    render(<Harness onValue={seen} />);
    const input = screen.getByLabelText("Upload a file for Grading rubric");
    await userEvent.upload(input, pdf());
    await screen.findByTestId("uploaded-file-name");

    extract.mockResolvedValue({ filename: "new.docx", text: "second file text", char_count: 16 });
    await userEvent.upload(input, new File(["x"], "new.docx"));
    await waitFor(() => expect(screen.getByTestId("uploaded-file-name")).toHaveTextContent("new.docx"));
    expect(seen).toHaveBeenLastCalledWith("second file text");
    expect(screen.getByRole("button", { name: "Replace file" })).toBeInTheDocument();
  });

  it("shows the problem and keeps the box when the upload fails", async () => {
    vi.spyOn(api, "extractFile").mockRejectedValue(new Error("No text could be extracted from this PDF."));
    render(<Harness />);
    await userEvent.upload(screen.getByLabelText("Upload a file for Grading rubric"), pdf());

    expect(await screen.findByRole("alert")).toHaveTextContent("No text could be extracted");
    expect(screen.queryByTestId("uploaded-file-name")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Grading rubric")).toBeInTheDocument();
  });

  it("forgets the file when the page clears the text", async () => {
    mockExtract();
    function Parent() {
      const [value, setValue] = useState("");
      return (
        <>
          <FileOrTextInput label="Grading rubric" value={value} onChange={setValue} />
          <button type="button" onClick={() => setValue("")}>Start over</button>
        </>
      );
    }
    render(<Parent />);
    await userEvent.upload(screen.getByLabelText("Upload a file for Grading rubric"), pdf());
    await screen.findByTestId("uploaded-file-name");
    await userEvent.click(screen.getByRole("button", { name: "Start over" }));
    expect(screen.queryByTestId("uploaded-file-name")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Grading rubric")).toBeInTheDocument();
  });
});
