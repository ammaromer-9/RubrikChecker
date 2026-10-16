import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import FileOrTextInput from "../components/FileOrTextInput";
import { Button, ErrorBanner, PageHeader, Spinner } from "../components/ui";

export default function NewAssignmentPage() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [instructions, setInstructions] = useState("");
  const [rubric, setRubric] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api.createAssignment({ title, instructions_text: instructions, rubric_raw_text: rubric }),
    onSuccess: (assignment) =>
      navigate(`/assignments/${assignment.id}/rubric`, { state: { autoParse: true } }),
  });

  const ready = title.trim() && instructions.trim() && rubric.trim();

  return (
    <>
      <PageHeader
        title="Check your draft before you submit it"
        subtitle="Add your assignment instructions and rubric. You'll review how we read the rubric before anything is graded."
      />
      <form
        className="space-y-6"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) create.mutate();
        }}
      >
        <label className="block text-sm font-medium text-slate-800">
          Assignment title
          <input
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white p-2.5 font-normal shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Persuasive essay on school phone policies"
          />
        </label>
        <FileOrTextInput
          label="Assignment instructions"
          value={instructions}
          onChange={setInstructions}
          placeholder="Paste the instructions from your teacher, or upload them."
        />
        <FileOrTextInput
          label="Grading rubric"
          value={rubric}
          onChange={setRubric}
          placeholder="Paste the rubric, or upload it. Tables from Word documents work too."
        />
        <ErrorBanner message={create.error?.message} />
        <Button type="submit" disabled={!ready || create.isPending}>
          {create.isPending && <Spinner className="h-4 w-4" />}
          Continue to rubric review
        </Button>
      </form>
    </>
  );
}
