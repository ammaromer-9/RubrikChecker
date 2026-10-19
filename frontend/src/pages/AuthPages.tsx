import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { Button, ErrorBanner, Spinner } from "../components/ui";

const FIELD =
  "mt-1 block w-full rounded-md border border-slate-300 bg-white p-2.5 text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500";

function AuthCard({ title, children, footer }: { title: string; children: ReactNode; footer: ReactNode }) {
  return (
    <div className="mx-auto max-w-md">
      <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        <div className="mt-5">{children}</div>
      </div>
      <p className="mt-4 text-center text-sm text-slate-600">{footer}</p>
    </div>
  );
}

/** Where to go after signing in: the page that sent you here, or your projects. */
function useDestination(): string {
  const from = (useLocation().state as { from?: string } | null)?.from;
  return from && from.startsWith("/") && !from.startsWith("//") ? from : "/projects";
}

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const destination = useDestination();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={destination} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(destination, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not sign in.");
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Sign in"
      footer={<>New here? <Link className="text-indigo-700 underline" to="/register">Create an account</Link></>}
    >
      <form onSubmit={(e) => void submit(e)} className="space-y-4">
        <label className="block text-sm font-medium text-slate-800">
          Email
          <input className={FIELD} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="block text-sm font-medium text-slate-800">
          Password
          <input className={FIELD} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <ErrorBanner message={error} />
        <Button type="submit" className="w-full" disabled={busy || !email || !password}>
          {busy && <Spinner className="h-4 w-4" />}
          Sign in
        </Button>
      </form>
    </AuthCard>
  );
}

export function RegisterPage() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const destination = useDestination();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={destination} replace />;

  const tooShort = password.length > 0 && password.length < 10;
  const mismatch = confirm.length > 0 && confirm !== password;
  const ready = email && password.length >= 10 && confirm === password && !busy;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      await register(email, password, name);
      navigate(destination, { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the account.");
      setBusy(false);
    }
  }

  return (
    <AuthCard
      title="Create your account"
      footer={<>Already have an account? <Link className="text-indigo-700 underline" to="/login">Sign in</Link></>}
    >
      <form onSubmit={(e) => void submit(e)} className="space-y-4">
        <label className="block text-sm font-medium text-slate-800">
          Name <span className="font-normal text-slate-500">(optional)</span>
          <input className={FIELD} autoComplete="name" maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="block text-sm font-medium text-slate-800">
          Email
          <input className={FIELD} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <div>
          <label className="block text-sm font-medium text-slate-800">
            Password
            <input className={FIELD} type="password" autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} aria-describedby="password-help" />
          </label>
          <p id="password-help" className={`mt-1 text-xs ${tooShort ? "text-red-700" : "text-slate-500"}`}>
            At least 10 characters. A few random words make a good password.
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-800">
            Confirm password
            <input className={FIELD} type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} aria-describedby={mismatch ? "confirm-help" : undefined} aria-invalid={mismatch} />
          </label>
          {mismatch && <p id="confirm-help" className="mt-1 text-xs text-red-700">The passwords don&apos;t match.</p>}
        </div>
        <p className="text-xs text-slate-500">
          There is no password reset yet, so keep your password somewhere safe.
        </p>
        <ErrorBanner message={error} />
        <Button type="submit" className="w-full" disabled={!ready}>
          {busy && <Spinner className="h-4 w-4" />}
          Create account
        </Button>
      </form>
    </AuthCard>
  );
}
