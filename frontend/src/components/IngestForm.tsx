"use client";

import { useRef, useState } from "react";
import { ingestFile, seedDemoIngest, type Entity, type Run } from "@/lib/api";
import { Button } from "./ui";

const ACCEPT = ".csv,.json,.xlsx,.xlsm";

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function IngestForm({
  entities,
  onRun,
}: {
  entities: Entity[];
  onRun: (run: Run) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<number[]>(entities.map((e) => e.id));
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function toggle(id: number) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  function pick(f: File | null) {
    setError(null);
    setFile(f);
  }

  async function submit() {
    setError(null);
    if (!file) {
      setError("Choose a file to ingest.");
      return;
    }
    if (selected.length === 0) {
      setError("Pick at least one target entity.");
      return;
    }
    setBusy(true);
    try {
      onRun(await ingestFile(file, selected));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function loadDemo() {
    setError(null);
    setBusy(true);
    try {
      onRun(await seedDemoIngest());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="mb-3 text-xs text-muted">
        Drop any export — a POS revenue file, a stock count, a supplier invoice. Canopy infers what
        it is and drafts a balanced journal per entity. No per-source setup.
      </p>

      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          pick(e.dataTransfer.files?.[0] ?? null);
        }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors ${
          dragging
            ? "border-emerald-400 bg-emerald-50"
            : "border-border-strong bg-surface-sunken hover:border-emerald-300"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => pick(e.target.files?.[0] ?? null)}
        />
        {file ? (
          <div className="flex items-center gap-2">
            <span className="text-lg">📄</span>
            <div className="text-left">
              <p className="text-sm font-medium text-slate-800">{file.name}</p>
              <p className="text-xs text-muted">{humanSize(file.size)} · click to replace</p>
            </div>
          </div>
        ) : (
          <>
            <span className="text-xl">⬆️</span>
            <p className="mt-1 text-sm font-medium text-slate-700">Drop a file or click to browse</p>
            <p className="text-xs text-muted">CSV · JSON · xlsx</p>
          </>
        )}
      </label>

      <div className="mt-3">
        <p className="mb-1.5 text-xs font-medium text-slate-500">Target entities</p>
        {entities.length === 0 ? (
          <p className="text-xs text-muted">No entities connected.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {entities.map((e) => (
              <button
                key={e.id}
                onClick={() => toggle(e.id)}
                className={`rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${
                  selected.includes(e.id)
                    ? "bg-emerald-600 text-white ring-emerald-600"
                    : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
                }`}
              >
                {e.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      <div className="mt-3 flex items-center gap-2">
        <Button onClick={submit} disabled={busy || entities.length === 0}>
          {busy ? "Inferring…" : "Infer & propose"}
        </Button>
        <Button variant="ghost" onClick={loadDemo} disabled={busy} className="!px-2.5 !py-2 text-xs">
          Load demo ingest
        </Button>
      </div>
    </div>
  );
}
