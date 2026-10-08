"use client";

import { useState } from "react";
import { api, type TrackingCategory } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Button, Card, ErrorNote, Loading } from "@/components/ui";

// Xero allows two active tracking categories per organisation, so the
// standard holds two at most (the API enforces it; this just explains it).
const MAX_ACTIVE = 2;

export function TrackingStandard({ ws, isAdmin }: { ws: string; isAdmin: boolean }) {
  const standard = useData(() => api.trackingStandard(ws));
  const [error, setError] = useState<string | null>(null);

  if (!standard.data) return <Loading />;
  const categories = standard.data;
  const active = categories.filter((c) => c.status === "active").length;

  async function run(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await standard.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <section className="mt-10">
      <h2 className="text-sm font-semibold text-slate-900">Tracking categories</h2>
      <p className="mb-3 text-sm text-muted">
        The tracking categories and options every organisation should have, for example Region or Department.
        Xero allows {MAX_ACTIVE} active categories per organisation, so the standard holds {MAX_ACTIVE} at most.
      </p>
      <ErrorNote message={error ?? standard.error} />
      {categories.length === 0 && (
        isAdmin ? <SeedTracking ws={ws} run={run} /> : <Card className="p-6 text-sm text-muted">No tracking categories in the standard yet.</Card>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        {categories.map((c) => <CategoryCard key={c.id} ws={ws} category={c} isAdmin={isAdmin} canRestore={active < MAX_ACTIVE} run={run} />)}
      </div>
      {isAdmin && active < MAX_ACTIVE && <AddCategory run={(name) => run(() => api.addTrackingCategory(ws, name))} />}
    </section>
  );
}

function SeedTracking({ ws, run }: { ws: string; run: (fn: () => Promise<unknown>) => Promise<void> }) {
  const entities = useData(() => api.entities(ws));
  const [entityId, setEntityId] = useState("");
  const synced = (entities.data ?? []).filter((e) => e.sync_status === "ok");
  return (
    <Card className="mb-4 space-y-3 p-5">
      <h3 className="text-sm font-semibold text-slate-900">Start from one organisation&apos;s tracking</h3>
      <p className="text-sm text-muted">Copies its active tracking categories and options. Or add a category below.</p>
      <div className="flex gap-2">
        <select value={entityId} onChange={(e) => setEntityId(e.target.value)} aria-label="Organisation to copy tracking from"
          className="flex-1 rounded-lg border border-border-strong px-3 py-2 text-sm">
          <option value="">Choose an organisation…</option>
          {synced.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </select>
        <Button disabled={!entityId} onClick={() => run(() => api.seedTracking(ws, entityId))}>Use its tracking</Button>
      </div>
    </Card>
  );
}

function CategoryCard({ ws, category, isAdmin, canRestore, run }: {
  ws: string; category: TrackingCategory; isAdmin: boolean; canRestore: boolean;
  run: (fn: () => Promise<unknown>) => Promise<void>;
}) {
  const [option, setOption] = useState("");
  const archived = category.status === "archived";
  return (
    <Card className={`space-y-3 p-4 ${archived ? "opacity-70" : ""}`}>
      <div className="flex items-start justify-between gap-2">
        <Renamable label={`Rename ${category.name}`} value={category.name} editable={isAdmin && !archived}
          onSave={(name) => run(() => api.editTrackingCategory(ws, category.id, { name }))}
          render={<span className="font-medium text-slate-900">{category.name} {archived && <Badge>archived</Badge>}</span>} />
        {isAdmin && (archived ? (
          <Button variant="ghost" disabled={!canRestore}
            onClick={() => run(() => api.editTrackingCategory(ws, category.id, { status: "active" }))}>Restore</Button>
        ) : (
          <Button variant="ghost" onClick={() => run(() => api.editTrackingCategory(ws, category.id, { status: "archived" }))}>Archive</Button>
        ))}
      </div>
      <ul className="divide-y divide-border rounded-lg border border-border">
        {category.options.length === 0 && <li className="px-3 py-2 text-sm text-muted">No options yet.</li>}
        {category.options.map((o) => (
          <li key={o.id} className="flex items-center justify-between gap-2 px-3 py-1.5 text-sm">
            <Renamable label={`Rename ${o.name}`} value={o.name} editable={isAdmin && o.status === "active"}
              onSave={(name) => run(() => api.editTrackingOption(ws, o.id, { name }))}
              render={<span className={o.status === "archived" ? "text-muted line-through" : ""}>{o.name}</span>} />
            {isAdmin && (
              <button className="text-xs text-slate-600 underline"
                onClick={() => run(() => api.editTrackingOption(ws, o.id, { status: o.status === "archived" ? "active" : "archived" }))}>
                {o.status === "archived" ? "Restore" : "Archive"}
              </button>
            )}
          </li>
        ))}
      </ul>
      {isAdmin && !archived && (
        <form className="flex gap-2" onSubmit={async (e) => { e.preventDefault(); await run(() => api.addTrackingOption(ws, category.id, option)); setOption(""); }}>
          <input value={option} onChange={(e) => setOption(e.target.value)} placeholder="New option" maxLength={100} required
            aria-label={`New option for ${category.name}`} className="flex-1 rounded-lg border border-border-strong px-3 py-1.5 text-sm" />
          <Button type="submit" variant="ghost">Add option</Button>
        </form>
      )}
    </Card>
  );
}

function Renamable({ value, editable, onSave, render, label }: {
  value: string; editable: boolean; onSave: (name: string) => Promise<void>; render: React.ReactNode; label: string;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(value);
  if (!editing) {
    return (
      <span className="flex items-center gap-2">
        {render}
        {editable && <button className="text-xs text-slate-500 underline" onClick={() => { setName(value); setEditing(true); }}>Rename</button>}
      </span>
    );
  }
  return (
    <form className="flex flex-1 gap-1" onSubmit={async (e) => { e.preventDefault(); await onSave(name); setEditing(false); }}>
      <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required aria-label={label} autoFocus
        className="flex-1 rounded border border-border-strong px-2 py-1 text-sm" />
      <Button type="submit" variant="ghost">Save</Button>
      <Button type="button" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
    </form>
  );
}

function AddCategory({ run }: { run: (name: string) => Promise<void> }) {
  const [name, setName] = useState("");
  return (
    <Card className="mt-4 p-4">
      <form className="flex gap-2" onSubmit={async (e) => { e.preventDefault(); await run(name); setName(""); }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Tracking category, e.g. Region" maxLength={100} required
          aria-label="New tracking category" className="flex-1 rounded-lg border border-border-strong px-3 py-2 text-sm" />
        <Button type="submit">Add category</Button>
      </form>
    </Card>
  );
}
