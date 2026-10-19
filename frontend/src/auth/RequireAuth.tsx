import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { LoadingPanel } from "../components/ui";
import { useAuth } from "./AuthContext";

/** Shows its children only to signed-in users; everyone else is sent to sign in, then back here. */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <LoadingPanel title="Loading…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}
