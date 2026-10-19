import { useState } from "react";
import { Link, NavLink } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import ThemeToggle from "./ThemeToggle";

const navLink = ({ isActive }: { isActive: boolean }) =>
  `rounded-md px-2 py-1 text-sm font-medium ${isActive ? "text-indigo-700" : "text-slate-600 hover:text-slate-900"}`;

/**
 * The bar at the top of every page. It is sticky, so the dark-mode switch is always on screen.
 */
export default function AppHeader() {
  const { user, logout } = useAuth();
  const [signOutError, setSignOutError] = useState<string | null>(null);

  // Once the user is gone, pages that need an account send you to sign in; public pages stay as they are.
  async function signOut() {
    setSignOutError(null);
    try {
      await logout();
    } catch (e) {
      setSignOutError(e instanceof Error ? e.message : "Could not sign out.");
    }
  }

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
        <div className="flex items-center gap-4">
          <Link to={user ? "/projects" : "/"} className="text-lg font-bold tracking-tight text-indigo-700">
            RubricCheck
          </Link>
          {user && (
            <nav aria-label="Main" className="flex items-center gap-1">
              <NavLink to="/projects" className={navLink}>
                Projects
              </NavLink>
            </nav>
          )}
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <ThemeToggle />
          {user ? (
            <>
              <span className="hidden max-w-[12rem] truncate text-sm text-slate-600 md:inline" title={user.email}>
                {user.display_name || user.email}
              </span>
              <button
                type="button"
                onClick={() => void signOut()}
                className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-700 hover:text-slate-900">
                Sign in
              </Link>
              <Link
                to="/register"
                className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
              >
                Create account
              </Link>
            </>
          )}
        </div>
      </div>
      {signOutError && (
        <p role="alert" className="border-t border-red-200 bg-red-50 px-4 py-2 text-center text-sm text-red-800">
          Couldn&apos;t sign you out: {signOutError} You&apos;re still signed in. Try again.
        </p>
      )}
    </header>
  );
}
