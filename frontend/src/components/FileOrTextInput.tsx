import { useRef, useState } from "react";

import { api } from "../api/client";
import { ErrorBanner, Spinner } from "./ui";

interface Props {
  label: string;
  value: string;
  onChange: (text: string) => void;
  placeholder?: string;
  rows?: number;
  maxChars?: number;
}

/** A textarea with an "upload a file" shortcut (PDF, .docx or .txt) that fills it with the extracted text. */
export default function FileOrTextInput({ label, value, onChange, placeholder, rows = 8, maxChars }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const over = maxChars !== undefined && value.length > maxChars;

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const result = await api.extractFile(file);
      onChange(result.text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <label className="text-sm font-medium text-slate-800">
          {label}
          <textarea
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white p-3 font-normal text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            rows={rows}
            value={value}
            placeholder={placeholder}
            onChange={(e) => onChange(e.target.value)}
          />
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.txt"
          className="sr-only"
          aria-label={`Upload a file for ${label}`}
          onChange={(e) => void handleFile(e.target.files?.[0])}
        />
        <button
          type="button"
          disabled={uploading}
          onClick={() => inputRef.current?.click()}
          className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-slate-700 hover:bg-slate-50 disabled:text-slate-400"
        >
          {uploading && <Spinner className="h-4 w-4" />}
          {uploading ? "Reading file…" : "Upload PDF, Word or text file"}
        </button>
        <span className={over ? "font-medium text-red-700" : "text-slate-500"}>
          {value.length.toLocaleString()}
          {maxChars !== undefined && ` / ${maxChars.toLocaleString()}`} characters
        </span>
      </div>
      {error && <div className="mt-2"><ErrorBanner message={error} /></div>}
    </div>
  );
}
