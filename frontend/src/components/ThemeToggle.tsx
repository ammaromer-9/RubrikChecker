import { useTheme } from "../lib/theme";

const Sun = () => (
  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
);

const Moon = () => (
  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </svg>
);

/** The light/dark switch. It lives in the header, which is always on screen. */
export default function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button
      type="button"
      role="switch"
      aria-checked={dark}
      aria-label="Dark mode"
      title={dark ? "Switch to light mode" : "Switch to dark mode"}
      onClick={toggle}
      className="inline-flex items-center gap-2 rounded-full border border-slate-300 bg-white px-2 py-1 text-sm text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
    >
      <span className="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full bg-slate-300" aria-hidden="true">
        <span
          className={`absolute left-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-white text-slate-700 shadow transition-transform ${dark ? "translate-x-4" : ""}`}
        >
          {dark ? <Moon /> : <Sun />}
        </span>
      </span>
      <span className="hidden pr-1 sm:inline">{dark ? "Dark" : "Light"}</span>
    </button>
  );
}
