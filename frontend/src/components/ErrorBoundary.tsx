import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  failed: boolean;
}

/** Shows a friendly message instead of a blank page if a component throws while rendering. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled UI error", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-6 text-red-900">
        <h2 className="text-lg font-semibold">Something went wrong showing this page</h2>
        <p className="mt-1 text-sm">Your work is saved. Reload the page to try again.</p>
        <button
          type="button"
          className="mt-3 rounded-md bg-red-700 px-4 py-2 text-sm font-medium text-white hover:bg-red-800"
          onClick={() => window.location.reload()}
        >
          Reload
        </button>
      </div>
    );
  }
}
