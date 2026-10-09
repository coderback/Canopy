"use client";

import { useState } from "react";
import { api, type TrackingCategory } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Button, Card, EmptyState, ErrorNote, Icon, Input, Loading, Notice, Select } from "@/components/ui";

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
    <section>
      <Notice tone="info" className="mb-4">
        The tracking categories and options every organisation should have, for example Region or Department. Xero allows {MAX_ACTIVE} active
        categories per organisation, so the standard holds {MAX_ACTIVE} at most ({active} of {MAX_ACTIVE} in use).
      </Notice>
      <ErrorNote message={error ?? standard.error} />
      {categories.length === 0 && (
        isAdmin ? <SeedTracking ws={ws} run={run} /> : <Card><EmptyState icon="tag" title="No tracking categories yet">An admin can add them.</EmptyState></Card>
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
    <Card padded className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand-strong"><Icon name="building" size={20} /></span>
      <div className="flex-1">
        <h3 className="text-[15px] font-semibold">Start from one organisation&apos;s tracking</h3>
        <p className="mt-0.5 text-sm text-muted">Copies its active tracking categories and options. Or add a category below.</p>
      </div>
      <div className="flex gap-2 sm:w-96">
        <Select value={entityId} onChange={(e) => setEntityId(e.target.value)} aria-label="Organisation to copy tracking from">
          <option value="">Choose an organisation…</option>
          {synced.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </Select>
        <Button disabled={!entityId} onClick={() => run(() => api.seedTracking(ws, entityId))}>Copy</Button>
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
    <Card className={`flex flex-col overflow-hidden ${archived ? "opacity-70" : ""}`}>
      <div className="flex items-start justify-between gap-2 border-b border-border bg-surface-sunken/50 px-4 py-3">
        <Renamable label={`Rename ${category.name}`} value={category.name} editable={isAdmin && !archived}
          onSave={(name) => run(() => api.editTrackingCategory(ws, category.id, { name }))}
          render={<span className="flex items-center gap-2 font-semibold"><Icon name="tag" size={16} className="text-brand" />{category.name} {archived && <Badge>Archived</Badge>}</span>} />
        {isAdmin && (archived ? (
          <Button variant="ghost" size="sm" disabled={!canRestore}
            onClick={() => run(() => api.editTrackingCategory(ws, category.id, { status: "active" }))}>Restore</Button>
        ) : (
          <Button variant="ghost" size="sm" icon="archive" onClick={() => run(() => api.editTrackingCategory(ws, category.id, { status: "archived" }))}>Archive</Button>
        ))}
      </div>
      <ul className="flex-1 divide-y divide-border">
        {category.options.length === 0 && <li className="px-4 py-4 text-sm text-muted">No options yet.</li>}
        {category.options.map((o) => (
          <li key={o.id} className="flex items-center justify-between gap-2 px-4 py-2.5 text-sm">
            <Renamable label={`Rename ${o.name}`} value={o.name} editable={isAdmin && o.status === "active"}
              onSave={(name) => run(() => api.editTrackingOption(ws, o.id, { name }))}
              render={<span className={o.status === "archived" ? "text-muted line-through" : ""}>{o.name}</span>} />
            {isAdmin && (
              <button className="text-xs text-muted transition hover:text-foreground"
                onClick={() => run(() => api.editTrackingOption(ws, o.id, { status: o.status === "archived" ? "active" : "archived" }))}>
                {o.status === "archived" ? "Restore" : "Archive"}
              </button>
            )}
          </li>
        ))}
      </ul>
      {isAdmin && !archived && (
        <form className="flex gap-2 border-t border-border bg-surface-sunken/40 p-3" onSubmit={async (e) => { e.preventDefault(); await run(() => api.addTrackingOption(ws, category.id, option)); setOption(""); }}>
          <Input value={option} onChange={(e) => setOption(e.target.value)} placeholder="Add an option…" maxLength={100} required
            aria-label={`New option for ${category.name}`} />
          <Button type="submit" variant="outline" icon="plus">Add</Button>
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
      <span className="group/ren flex items-center gap-2">
        {render}
        {editable && (
          <button aria-label={label} title="Rename" className="rounded-md p-1 text-subtle opacity-0 transition hover:bg-surface-sunken hover:text-foreground focus-visible:opacity-100 group-hover/ren:opacity-100"
            onClick={() => { setName(value); setEditing(true); }}>
            <Icon name="edit" size={14} />
          </button>
        )}
      </span>
    );
  }
  return (
    <form className="flex flex-1 gap-1.5" onSubmit={async (e) => { e.preventDefault(); await onSave(name); setEditing(false); }}>
      <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required aria-label={label} autoFocus className="h-8" />
      <Button type="submit" size="sm">Save</Button>
      <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
    </form>
  );
}

function AddCategory({ run }: { run: (name: string) => Promise<void> }) {
  const [name, setName] = useState("");
  return (
    <Card padded className="mt-4">
      <form className="flex gap-2" onSubmit={async (e) => { e.preventDefault(); await run(name); setName(""); }}>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="New tracking category, e.g. Region" maxLength={100} required
          aria-label="New tracking category" />
        <Button type="submit" icon="plus">Add category</Button>
      </form>
    </Card>
  );
}
