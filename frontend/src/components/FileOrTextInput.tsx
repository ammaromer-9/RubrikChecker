import { useEffect, useRef, useState } from "react";

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

/**
 * A textarea with an "upload a file" shortcut (PDF, .docx or .txt).
 *
 * An uploaded file's text is read on the server and passed up through `onChange`, but the
 * box only shows the file's name, not its contents. Remove the file to type or paste instead.
 */
export default function FileOrTextInput({ label, value, onChange, placeholder, rows = 8, maxChars }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const over = maxChars !== undefined && value.length > maxChars;

  // If the parent clears the text (for example after starting over), forget the file too.
  useEffect(() => {
    if (value === "") setFileName(null);
  }, [value]);

  async function handleFile(file: File | undefined) {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const result = await api.extractFile(file);
      setFileName(file.name);
      onChange(result.text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = ""; // lets the same file be chosen again
    }
  }

  function removeFile() {
    setFileName(null);
    setError(null);
    onChange("");
  }

  const count = (
    <span className={over ? "font-medium text-red-700" : "text-slate-500"}>
      {value.length.toLocaleString()}
      {maxChars !== undefined && ` / ${maxChars.toLocaleString()}`} characters
    </span>
  );

  return (
    <div>
      {fileName === null ? (
        <label className="mb-1 block text-sm font-medium text-slate-800">
          {label}
          <textarea
            className="mt-1 block w-full rounded-md border border-slate-300 bg-white p-3 font-normal text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            rows={rows}
            value={value}
            placeholder={placeholder}
            onChange={(e) => onChange(e.target.value)}
          />
        </label>
      ) : (
        <div>
          <p className="mb-1 text-sm font-medium text-slate-800">{label}</p>
          <div
            role="group"
            aria-label={`Uploaded file for ${label}`}
            className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-300 bg-white px-4 py-3 shadow-sm"
          >
            <div className="min-w-0">
              <p className="truncate font-medium text-slate-900" data-testid="uploaded-file-name">
                {fileName}
              </p>
              <p className="text-sm text-slate-500">{count}</p>
            </div>
            <button
              type="button"
              onClick={removeFile}
              disabled={uploading}
              className="rounded-md border border-red-200 bg-white px-3 py-1.5 text-sm text-red-700 hover:bg-red-50 disabled:text-slate-400"
            >
              Remove file
            </button>
          </div>
        </div>
      )}
      <div className="mt-1 flex flex-wrap items-center gap-3 text-sm">
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
          {uploading ? "Reading file…" : fileName === null ? "Upload PDF, Word or text file" : "Replace file"}
        </button>
        {fileName === null && count}
      </div>
      {error && <div className="mt-2"><ErrorBanner message={error} /></div>}
    </div>
  );
}
