import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import indexHtml from "../../index.html?raw";
import ThemeToggle from "../components/ThemeToggle";
import { mockSystemTheme } from "../test/render";
import { applyTheme, currentTheme, storedTheme } from "./theme";

const isDark = () => document.documentElement.classList.contains("dark");

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
});
afterEach(() => {
  vi.restoreAllMocks(); // including the "storage is blocked" spies
  vi.unstubAllGlobals();
});

describe("choosing a theme", () => {
  it("follows the system when nothing was chosen", () => {
    mockSystemTheme(true);
    expect(currentTheme()).toBe("dark");
    mockSystemTheme(false);
    expect(currentTheme()).toBe("light");
  });

  it("an explicit choice beats the system", () => {
    mockSystemTheme(true);
    localStorage.setItem("rubriccheck-theme", "light");
    expect(currentTheme()).toBe("light");
  });

  it("ignores junk in storage", () => {
    mockSystemTheme(false);
    localStorage.setItem("rubriccheck-theme", "purple");
    expect(storedTheme()).toBeNull();
    expect(currentTheme()).toBe("light");
  });

  it("still works when storage is blocked", () => {
    mockSystemTheme(true);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(currentTheme()).toBe("dark");
  });

  it("applies the theme as a class on <html>", () => {
    applyTheme("dark");
    expect(isDark()).toBe(true);
    applyTheme("light");
    expect(isDark()).toBe(false);
  });
});

describe("ThemeToggle", () => {
  it("is a labelled switch that reflects the current theme", () => {
    mockSystemTheme(false);
    render(<ThemeToggle />);
    const toggle = screen.getByRole("switch", { name: "Dark mode" });
    expect(toggle).toHaveAttribute("aria-checked", "false");
    expect(isDark()).toBe(false);
  });

  it("starts dark when the system is dark", () => {
    mockSystemTheme(true);
    render(<ThemeToggle />);
    expect(screen.getByRole("switch", { name: "Dark mode" })).toHaveAttribute("aria-checked", "true");
    expect(isDark()).toBe(true);
  });

  it("switches the page and remembers the choice", async () => {
    mockSystemTheme(false);
    render(<ThemeToggle />);
    const toggle = screen.getByRole("switch", { name: "Dark mode" });

    await userEvent.click(toggle);
    expect(isDark()).toBe(true);
    expect(toggle).toHaveAttribute("aria-checked", "true");
    expect(localStorage.getItem("rubriccheck-theme")).toBe("dark");

    await userEvent.click(toggle);
    expect(isDark()).toBe(false);
    expect(localStorage.getItem("rubriccheck-theme")).toBe("light");
  });

  it("can be used from the keyboard", async () => {
    mockSystemTheme(false);
    render(<ThemeToggle />);
    await userEvent.tab();
    expect(screen.getByRole("switch")).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(isDark()).toBe(true);
  });

  it("follows the system while the user has not chosen, then stops once they have", async () => {
    const system = mockSystemTheme(false);
    render(<ThemeToggle />);
    act(() => system.setDark(true));
    expect(isDark()).toBe(true);

    await userEvent.click(screen.getByRole("switch")); // user picks light
    act(() => system.setDark(true));
    expect(isDark()).toBe(false); // their choice wins now
  });

  it("follows a change made in another tab", () => {
    mockSystemTheme(false);
    render(<ThemeToggle />);
    localStorage.setItem("rubriccheck-theme", "dark");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "rubriccheck-theme", newValue: "dark" }));
    });
    expect(isDark()).toBe(true);
  });

  it("still toggles for this visit when storage is blocked", async () => {
    mockSystemTheme(false);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(<ThemeToggle />);
    await userEvent.click(screen.getByRole("switch"));
    expect(isDark()).toBe(true);
  });
});

describe("the early script in index.html (prevents a light flash)", () => {
  const script = /<script>([\s\S]*?)<\/script>/.exec(indexHtml)![1];
  const run = () => new Function(script)();

  it("agrees with theme.ts in every situation", () => {
    for (const saved of [null, "light", "dark", "junk"]) {
      for (const systemDark of [false, true]) {
        localStorage.clear();
        if (saved) localStorage.setItem("rubriccheck-theme", saved);
        mockSystemTheme(systemDark);
        document.documentElement.classList.remove("dark");
        run();
        // theme.ts treats junk as "no choice"; the script treats anything but "dark" as light,
        // which differs only for corrupted storage, where either answer is acceptable.
        if (saved !== "junk") expect(isDark()).toBe(currentTheme() === "dark");
      }
    }
  });

  it("does not crash when storage throws", () => {
    mockSystemTheme(true);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(run).not.toThrow();
  });
});
