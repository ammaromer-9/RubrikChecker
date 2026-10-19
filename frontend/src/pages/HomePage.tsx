import { Link } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

const STEPS = [
  { title: "Add your assignment", body: "Paste or upload the instructions and the rubric. You check how the rubric was read before anything is graded." },
  { title: "Submit a draft", body: "Get a predicted score for every criterion, with a likely range and the exact passages that justify it." },
  { title: "Improve and try again", body: "Each project keeps every attempt, so you can see your score change and which problems you fixed." },
];

const PRIMARY = "inline-block rounded-md bg-indigo-600 px-5 py-2.5 font-medium text-white hover:bg-indigo-700";
const SECONDARY = "inline-block rounded-md border border-slate-300 bg-white px-5 py-2.5 font-medium text-slate-700 hover:bg-slate-50";

export default function HomePage() {
  const { user, loading } = useAuth();
  return (
    <div className="space-y-14">
      <section className="py-6 text-center sm:py-12">
        <h1 className="mx-auto max-w-3xl text-3xl font-bold tracking-tight sm:text-5xl">
          Know how your draft will score before you hand it in
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-lg text-slate-600">
          RubricCheck predicts your grade against your own rubric and tells you what to fix. It coaches you with
          questions. It never writes or rewrites your work.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          {loading ? null : user ? (
            <Link to="/projects" className={PRIMARY}>Go to your projects</Link>
          ) : (
            <>
              <Link to="/register" className={PRIMARY}>Create a free account</Link>
              <Link to="/login" className={SECONDARY}>Sign in</Link>
            </>
          )}
        </div>
      </section>

      <section aria-label="How it works">
        <h2 className="text-center text-2xl font-bold">How it works</h2>
        <ol className="mt-6 grid gap-4 md:grid-cols-3">
          {STEPS.map((step, index) => (
            <li key={step.title} className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 text-sm font-bold text-indigo-700">
                {index + 1}
              </span>
              <h3 className="mt-3 text-lg font-semibold">{step.title}</h3>
              <p className="mt-1 text-sm text-slate-600">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-label="What to expect" className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-xl font-bold">What to expect</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-slate-700">
          <li>A score range, not a single number, and a flag on any criterion where the AI wasn&apos;t consistent.</li>
          <li>Every score points to quotes from your draft, checked against what you actually wrote.</li>
          <li>Feedback in the form of what&apos;s missing and questions to think about, never replacement text.</li>
          <li>It&apos;s a prediction, not your real grade. Your teacher&apos;s grade is what counts.</li>
        </ul>
      </section>
    </div>
  );
}
