"use client";

import type { Entity } from "@/lib/api";

/** Compact live status of every connected org — the multi-entity story, always
 * visible in the header rather than eating a full dashboard card. */
export default function EntityHealthBar({ entities }: { entities: Entity[] }) {
  if (entities.length === 0) {
    return (
      <span className="text-xs text-muted">
        No organisations connected —{" "}
        <code className="rounded bg-surface-sunken px-1 py-0.5">/auth/xero/connect</code>
      </span>
    );
  }
  return (
    <div className="flex items-center gap-3">
      <span className="hidden text-xs font-medium text-muted sm:inline">
        {entities.length} {entities.length === 1 ? "organisation" : "organisations"}
      </span>
      <div className="canopy-scroll flex max-w-[52vw] items-center gap-1.5 overflow-x-auto pb-0.5">
        {entities.map((e) => (
          <span
            key={e.id}
            title={e.snapshot_age ? `snapshot cached` : "no snapshot yet"}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-border bg-surface px-2.5 py-1 text-xs font-medium text-slate-700"
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                e.snapshot_age ? "bg-emerald-500" : "bg-amber-400"
              }`}
            />
            {e.name}
          </span>
        ))}
      </div>
    </div>
  );
}
