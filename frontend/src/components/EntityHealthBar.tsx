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
        {entities.map((e) => {
          const h = e.health;
          const drifted = (h?.drift_total ?? 0) > 0;
          const fullyCached = h != null && h.kinds_cached === h.kinds_total;
          const dot = drifted
            ? "bg-rose-500"
            : fullyCached
              ? "bg-emerald-500"
              : "bg-amber-400";
          return (
            <span
              key={e.id}
              title={healthTitle(e)}
              className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border bg-surface px-2.5 py-1 text-xs font-medium text-slate-700 ${
                drifted ? "border-rose-300" : "border-border"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
              {e.name}
              {drifted && (
                <span className="font-semibold text-rose-600">{h.drift_total}</span>
              )}
            </span>
          );
        })}
      </div>
    </div>
  );
}

/** Multi-line native tooltip: snapshot coverage + cross-org account drift. */
function healthTitle(e: Entity): string {
  const h = e.health;
  if (h == null || h.kinds_cached === 0) return "no snapshot yet";
  const lines = [`${h.kinds_cached}/${h.kinds_total} snapshot kinds cached`];
  for (const d of h.drift) {
    lines.push(
      `missing account ${d.code} · ${d.name} (present in ${d.present_in}/${d.of} orgs)`,
    );
  }
  if (h.drift_total > h.drift.length) {
    lines.push(`…and ${h.drift_total - h.drift.length} more drifted codes`);
  }
  return lines.join("\n");
}