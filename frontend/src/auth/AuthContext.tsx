import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, SESSION_EXPIRED_EVENT } from "../api/client";
import type { User } from "../api/types";

interface AuthValue {
  /** The signed-in user, or null when signed out. */
  user: User | null;
  /** True until we know whether there is a signed-in user (the first check on page load). */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((u) => !cancelled && setUser(u))
      .catch(() => !cancelled && setUser(null)) // 401 just means signed out
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  // The session ended (expired, or signed out in another tab): show the sign-in page.
  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      queryClient.clear();
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, [queryClient]);

  const login = useCallback(
    async (email: string, password: string) => {
      const signedIn = await api.login({ email, password });
      queryClient.clear(); // never show another account's cached data
      setUser(signedIn);
    },
    [queryClient],
  );

  const register = useCallback(
    async (email: string, password: string, displayName: string) => {
      const created = await api.register({ email, password, display_name: displayName });
      queryClient.clear();
      setUser(created);
    },
    [queryClient],
  );

  // Rejects if the server could not be reached: the session cookie would still be valid, so the user
  // is not shown as signed out when they are not.
  const logout = useCallback(async () => {
    await api.logout();
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  const value = useMemo(() => ({ user, loading, login, register, logout }), [user, loading, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
