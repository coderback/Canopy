"use client";

import type { Entity } from "@/lib/api";
import { Badge } from "./ui";

export default function EntitiesPanel({ entities }: { entities: Entity[] }) {
  return (
    <div className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">Entities</h2>
        <Badge tone="slate">{entities.length} connected</Badge>
      </div>
      {entities.length === 0 ? (
        <p className="text-xs text-muted">
          Connect Xero organisations via the backend&apos;s <code>/auth/xero/connect</code>, or load a
          demo run to preview the flow.
        </p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {entities.map((e) => (
            <li
              key={e.id}
              className="flex items-center gap-2 rounded-lg border border-border bg-slate-50 px-3 py-1.5"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              <span className="text-sm font-medium text-slate-800">{e.name}</span>
              <span className="text-xs text-muted">
                {e.snapshot_age ? "cached" : "no snapshot yet"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
