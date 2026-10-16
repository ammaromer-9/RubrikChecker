import { Link, Route, Routes } from "react-router-dom";

import ErrorBoundary from "./components/ErrorBoundary";
import ComparePage from "./pages/ComparePage";
import HistoryPage from "./pages/HistoryPage";
import NewAssignmentPage from "./pages/NewAssignmentPage";
import ResultsPage from "./pages/ResultsPage";
import ReviewRubricPage from "./pages/ReviewRubricPage";
import SubmitDraftPage from "./pages/SubmitDraftPage";

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <Link to="/" className="text-lg font-bold tracking-tight text-indigo-700">RubricCheck</Link>
          <span className="hidden text-sm text-slate-500 sm:inline">Pre-submission feedback that never writes it for you</span>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <ErrorBoundary>
        <Routes>
          <Route path="/" element={<NewAssignmentPage />} />
          <Route path="/assignments/:id/rubric" element={<ReviewRubricPage />} />
          <Route path="/assignments/:id/submit" element={<SubmitDraftPage />} />
          <Route path="/gradings/:id" element={<ResultsPage />} />
          <Route path="/assignments/:id/history" element={<HistoryPage />} />
          <Route path="/submissions/:id/compare/:previousId" element={<ComparePage />} />
          <Route path="*" element={<p className="text-slate-700">Page not found. <Link className="text-indigo-700 underline" to="/">Go home</Link></p>} />
        </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}
