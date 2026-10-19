import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, SESSION_EXPIRED_EVENT } from "../api/client";
import App from "../App";
import { AuthProvider } from "../auth/AuthContext";
import { ANA, mockSystemTheme, renderApp } from "../test/render";

beforeEach(() => {
  mockSystemTheme(false);
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  vi.spyOn(api, "listProjects").mockResolvedValue([]);
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const switchEl = () => screen.getByRole("switch", { name: "Dark mode" });

describe("the header and the dark-mode switch", () => {
  it.each([
    ["the homepage", "/", null],
    ["sign in", "/login", null],
    ["create account", "/register", null],
    ["your projects", "/projects", ANA],
    ["a new project", "/projects/new", ANA],
    ["an unknown page", "/nope", null],
  ])("shows the switch on %s", async (_name, path, user) => {
    renderApp(path, user);
    expect(await screen.findByRole("banner")).toContainElement(switchEl());
  });

  it("keeps the header (and so the switch) at the top while scrolling", async () => {
    renderApp("/", null);
    const header = await screen.findByRole("banner");
    expect(header.className).toMatch(/\bsticky\b/);
    expect(header.className).toMatch(/\btop-0\b/);
  });

  it("works from the header on any page", async () => {
    renderApp("/login", null);
    await userEvent.click(await screen.findByRole("switch", { name: "Dark mode" }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("offers sign in and create account to visitors", async () => {
    renderApp("/", null);
    const header = await screen.findByRole("banner");
    expect(within(header).getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(within(header).getByRole("link", { name: "Create account" })).toHaveAttribute("href", "/register");
    expect(within(header).queryByRole("button", { name: "Sign out" })).not.toBeInTheDocument();
    expect(within(header).getByRole("link", { name: "RubricCheck" })).toHaveAttribute("href", "/");
  });

  it("shows who is signed in, a Projects link and Sign out", async () => {
    renderApp("/projects", ANA);
    const header = await screen.findByRole("banner");
    expect(await within(header).findByText("Ana")).toBeInTheDocument();
    expect(within(header).getByRole("link", { name: "Projects" })).toHaveAttribute("href", "/projects");
    expect(within(header).getByRole("link", { name: "RubricCheck" })).toHaveAttribute("href", "/projects");
    expect(within(header).queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("falls back to the email when there is no display name", async () => {
    renderApp("/projects", { ...ANA, display_name: "" });
    expect(await within(await screen.findByRole("banner")).findByText("ana@example.com")).toBeInTheDocument();
  });

  it("signing out of a page that needs an account lands on sign in", async () => {
    const logout = vi.spyOn(api, "logout").mockResolvedValue(undefined);
    renderApp("/projects", ANA);
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(logout).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(within(screen.getByRole("banner")).getByRole("link", { name: "Create account" })).toBeInTheDocument();
  });

  it("signing out on the homepage stays there as a visitor", async () => {
    vi.spyOn(api, "logout").mockResolvedValue(undefined);
    renderApp("/", ANA);
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("link", { name: "Create a free account" })).toBeInTheDocument();
  });

  it("does not pretend you are signed out when the server could not be reached", async () => {
    vi.spyOn(api, "logout").mockRejectedValue(new ApiError(0, "Could not reach the server."));
    renderApp("/projects", ANA);
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't sign you out: Could not reach the server.");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument(); // still signed in
    expect(screen.getByRole("heading", { name: "Your projects" })).toBeInTheDocument();
  });
});

describe("the homepage", () => {
  it("invites visitors to create an account or sign in", async () => {
    renderApp("/", null);
    expect(await screen.findByRole("link", { name: "Create a free account" })).toHaveAttribute("href", "/register");
    expect(screen.getAllByRole("link", { name: "Sign in" }).length).toBeGreaterThan(0);
    expect(screen.getByText(/never writes or rewrites your work/)).toBeInTheDocument();
    expect(screen.getByText(/not your real grade/)).toBeInTheDocument();
  });

  it("sends signed-in users to their projects", async () => {
    renderApp("/", ANA);
    expect(await screen.findByRole("link", { name: "Go to your projects" })).toHaveAttribute("href", "/projects");
    expect(screen.queryByRole("link", { name: "Create a free account" })).not.toBeInTheDocument();
  });
});

describe("protected pages", () => {
  it("send visitors to sign in", async () => {
    renderApp("/projects", null);
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it.each(["/projects", "/projects/new", "/projects/3", "/projects/3/rubric", "/projects/3/submit", "/gradings/3", "/submissions/3/compare/2"])(
    "%s needs an account",
    async (path) => {
      renderApp(path, null);
      expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    },
  );

  it("take you back where you were going after you sign in", async () => {
    vi.spyOn(api, "login").mockResolvedValue(ANA);
    vi.spyOn(api, "getAssignment").mockRejectedValue(new ApiError(404, "Project not found."));
    vi.spyOn(api, "getHistory").mockRejectedValue(new ApiError(404, "Project not found."));
    renderApp("/projects/7", null);

    await userEvent.type(await screen.findByLabelText("Email"), "ana@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Project not found.")).toBeInTheDocument(); // we arrived at /projects/7
    expect(api.getAssignment).toHaveBeenCalledWith(7);
  });

  it("ignore a sign-in redirect that points to another website", async () => {
    vi.spyOn(api, "me").mockRejectedValue(new ApiError(401, "no"));
    vi.spyOn(api, "login").mockResolvedValue(ANA);
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[{ pathname: "/login", state: { from: "//evil.example/steal" } }]}>
          <AuthProvider>
            <App />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await userEvent.type(await screen.findByLabelText("Email"), "ana@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { name: "Your projects" })).toBeInTheDocument();
  });

  it("keep signed-in users out of the sign-in form", async () => {
    renderApp("/login", ANA);
    expect(await screen.findByRole("heading", { name: "Your projects" })).toBeInTheDocument();
  });

  it("send you to sign in when the session ends while you are using the app", async () => {
    renderApp("/projects", ANA);
    expect(await screen.findByRole("heading", { name: "Your projects" })).toBeInTheDocument();
    act(() => {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    });
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});

describe("signing in", () => {
  const fill = async (email = "ana@example.com", password = "correct horse battery") => {
    await userEvent.type(await screen.findByLabelText("Email"), email);
    await userEvent.type(screen.getByLabelText("Password"), password);
  };

  it("needs both fields before the button works", async () => {
    renderApp("/login", null);
    const button = await screen.findByRole("button", { name: "Sign in" });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Email"), "ana@example.com");
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Password"), "x");
    expect(button).toBeEnabled();
  });

  it("signs in and opens your projects", async () => {
    const login = vi.spyOn(api, "login").mockResolvedValue(ANA);
    renderApp("/login", null);
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(login).toHaveBeenCalledExactlyOnceWith({ email: "ana@example.com", password: "correct horse battery" });
    expect(await screen.findByRole("heading", { name: "Your projects" })).toBeInTheDocument();
  });

  it("shows the server's message when the details are wrong and lets you retry", async () => {
    vi.spyOn(api, "login").mockRejectedValue(new ApiError(401, "Incorrect email or password."));
    renderApp("/login", null);
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Incorrect email or password.");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
    expect(screen.getByLabelText("Email")).toHaveValue("ana@example.com"); // typed details are kept
  });

  it("explains a lockout", async () => {
    vi.spyOn(api, "login").mockRejectedValue(new ApiError(429, "Too many attempts. Try again in 15 minute(s)."));
    renderApp("/login", null);
    await fill();
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many attempts");
  });

  it("uses the right autocomplete hints so password managers work", async () => {
    renderApp("/login", null);
    expect(await screen.findByLabelText("Email")).toHaveAttribute("autocomplete", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });

  it("links to creating an account", async () => {
    renderApp("/login", null);
    expect(await screen.findByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/register");
  });
});

describe("creating an account", () => {
  const type = async (label: string | RegExp, text: string) => userEvent.type(await screen.findByLabelText(label), text);

  it("will not submit with a short or mismatched password", async () => {
    renderApp("/register", null);
    await type("Email", "ana@example.com");
    await type("Password", "short");
    const button = screen.getByRole("button", { name: "Create account" });
    expect(button).toBeDisabled();
    expect(screen.getByText(/At least 10 characters/)).toHaveClass("text-red-700");

    await userEvent.type(screen.getByLabelText("Password"), "-and-longer");
    await type("Confirm password", "different password");
    expect(screen.getByText("The passwords don't match.")).toBeInTheDocument();
    expect(button).toBeDisabled();

    await userEvent.clear(screen.getByLabelText("Confirm password"));
    await userEvent.type(screen.getByLabelText("Confirm password"), "short-and-longer");
    expect(button).toBeEnabled();
  });

  it("creates the account and signs you in", async () => {
    const register = vi.spyOn(api, "register").mockResolvedValue(ANA);
    renderApp("/register", null);
    await type(/^Name/, "Ana");
    await type("Email", "ana@example.com");
    await type("Password", "correct horse battery");
    await type("Confirm password", "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(register).toHaveBeenCalledExactlyOnceWith({ email: "ana@example.com", password: "correct horse battery", display_name: "Ana" });
    expect(await screen.findByRole("heading", { name: "Your projects" })).toBeInTheDocument();
  });

  it("shows when the email is already taken", async () => {
    vi.spyOn(api, "register").mockRejectedValue(new ApiError(409, "An account with this email already exists."));
    renderApp("/register", null);
    await type("Email", "ana@example.com");
    await type("Password", "correct horse battery");
    await type("Confirm password", "correct horse battery");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
    expect(screen.getByRole("button", { name: "Create account" })).toBeEnabled();
  });

  it("is honest that there is no password reset", async () => {
    renderApp("/register", null);
    expect(await screen.findByText(/no password reset yet/)).toBeInTheDocument();
  });

  it("uses new-password hints for password managers", async () => {
    renderApp("/register", null);
    expect(await screen.findByLabelText("Password")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByLabelText("Confirm password")).toHaveAttribute("autocomplete", "new-password");
  });
});

describe("api client and sessions", () => {
  it("announces an ended session on a 401 from a normal request", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Please sign in to continue." }), { status: 401 })));
    const heard = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, heard);
    await expect(api.getAssignment(3)).rejects.toMatchObject({ status: 401 });
    window.removeEventListener(SESSION_EXPIRED_EVENT, heard);
    expect(heard).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["checking who you are", () => api.me()],
    ["signing in", () => api.login({ email: "a@b.co", password: "x" })],
  ])("does not treat a 401 from %s as an ended session", async (_name, call) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "no" }), { status: 401 })));
    const heard = vi.fn();
    window.addEventListener(SESSION_EXPIRED_EVENT, heard);
    await expect(call()).rejects.toMatchObject({ status: 401 });
    window.removeEventListener(SESSION_EXPIRED_EVENT, heard);
    expect(heard).not.toHaveBeenCalled();
  });

  it("sends the session cookie with same-origin requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.getHistory(3);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "same-origin" });
  });

  it("handles responses with no body (sign out, delete)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(api.logout()).resolves.toBeUndefined();
    await expect(api.deleteProject(3)).resolves.toBeUndefined();
  });
});
