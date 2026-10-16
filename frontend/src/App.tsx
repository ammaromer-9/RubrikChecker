import { useEffect, useState } from "react";

import { api, type HealthResponse } from "./api/client";

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-3xl font-bold">RubricCheck</h1>
      <p className="mt-2 text-slate-600">Pre-submission grading assistant for students.</p>
      <p className="mt-6 text-sm">
        Backend:{" "}
        {error ? (
          <span className="text-red-600">unreachable ({error})</span>
        ) : health ? (
          <span className="text-green-700">
            {health.status} (database: {health.database})
          </span>
        ) : (
          "checking…"
        )}
      </p>
    </main>
  );
}
