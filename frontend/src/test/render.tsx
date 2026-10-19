import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { api } from "../api/client";
import type { User } from "../api/types";
import App from "../App";
import { AuthProvider } from "../auth/AuthContext";

export const ANA: User = { id: 1, email: "ana@example.com", display_name: "Ana", created_at: "2026-10-01T10:00:00Z" };

/** Renders the whole app at `path`, signed in as `user` (or signed out when null). */
export function renderApp(path: string, user: User | null = ANA) {
  vi.spyOn(api, "me").mockImplementation(async () => {
    if (!user) throw new (await import("../api/client")).ApiError(401, "Please sign in to continue.");
    return user;
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** A controllable stand-in for the browser's dark-mode preference (jsdom has none). */
export function mockSystemTheme(initiallyDark: boolean) {
  let dark = initiallyDark;
  const listeners = new Set<() => void>();
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches() {
      return query.includes("dark") ? dark : false;
    },
    media: query,
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  }));
  return {
    setDark(next: boolean) {
      dark = next;
      listeners.forEach((fn) => fn());
    },
  };
}
