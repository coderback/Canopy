"use client";

import type { Run } from "@/lib/api";
import { StatusPill } from "./ui";

export default function RunHistory({
  runs,
  activeId,
  onSelect,
}: {
  runs: Run[];
  activeId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <div className="p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-900">Run history</h2>
      {runs.length === 0 ? (
        <p className="text-xs text-muted">No runs yet.</p>
      ) : (
        <ul className="space-y-1.5">
          {runs.map((r) => (
            <li key={r.id}>
              <button
                onClick={() => onSelect(r.id)}
                className={`flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition-colors ${
                  activeId === r.id
                    ? "border-blue-300 bg-blue-50"
                    : "border-border bg-white hover:bg-slate-50"
                }`}
              >
                <span className="text-sm text-slate-700">
                  #{r.id} · {r.change_type ?? r.kind}
                </span>
                <StatusPill status={r.status} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
