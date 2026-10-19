import { Link, Route, Routes } from "react-router-dom";

import RequireAuth from "./auth/RequireAuth";
import AppHeader from "./components/AppHeader";
import ErrorBoundary from "./components/ErrorBoundary";
import { LoginPage, RegisterPage } from "./pages/AuthPages";
import ComparePage from "./pages/ComparePage";
import HomePage from "./pages/HomePage";
import NewAssignmentPage from "./pages/NewAssignmentPage";
import ProjectPage from "./pages/ProjectPage";
import ProjectsPage from "./pages/ProjectsPage";
import ResultsPage from "./pages/ResultsPage";
import ReviewRubricPage from "./pages/ReviewRubricPage";
import SubmitDraftPage from "./pages/SubmitDraftPage";

const protectedPage = (element: React.ReactNode) => <RequireAuth>{element}</RequireAuth>;

export default function App() {
  return (
    <div className="min-h-screen">
      <AppHeader />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />

            <Route path="/projects" element={protectedPage(<ProjectsPage />)} />
            <Route path="/projects/new" element={protectedPage(<NewAssignmentPage />)} />
            <Route path="/projects/:id" element={protectedPage(<ProjectPage />)} />
            <Route path="/projects/:id/rubric" element={protectedPage(<ReviewRubricPage />)} />
            <Route path="/projects/:id/submit" element={protectedPage(<SubmitDraftPage />)} />
            <Route path="/gradings/:id" element={protectedPage(<ResultsPage />)} />
            <Route path="/submissions/:id/compare/:previousId" element={protectedPage(<ComparePage />)} />

            <Route
              path="*"
              element={
                <p className="text-slate-700">
                  Page not found. <Link className="text-indigo-700 underline" to="/">Go home</Link>
                </p>
              }
            />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}
