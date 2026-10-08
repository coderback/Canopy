"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type ItemSpec, type TrackingCategory, type TrackingRow } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Button, Card, ErrorNote, Loading, SourceBadge } from "@/components/ui";

type Mapping = TrackingRow["mapping"];
type Choice = { id: string; name: string };

export function TrackingMapping({ ws, entity, orgName, isAdmin, canPropose }: {
  ws: string; entity: string; orgName: string; isAdmin: boolean; canPropose: boolean;
}) {
  const router = useRouter();
  const rows = useData(() => api.entityTracking(ws, entity));
  const standard = useData(() => api.trackingStandard(ws));
  const [error, setError] = useState<string | null>(null);

  if (!rows.data || !standard.data) return <Loading />;
  const groups = standard.data.filter((c) => c.status === "active");

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await rows.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  // One-click proposals start a draft for review; nothing is written until approved.
  async function propose(title: string, item: Omit<ItemSpec, "entity_id">) {
    setError(null);
    try {
      const change = await api.createChange(ws, title, [{ ...item, entity_id: entity } as ItemSpec]);
      router.push(`/w/${ws}/changes/${change.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const decide = (kind: "categories" | "options", m: NonNullable<Mapping>) =>
    (action: "confirm" | "reject" | "assign", groupId?: string | null) =>
      act(() => api.decideTracking(ws, kind, m.id, { action, group_id: groupId ?? null }));

  return (
    <section className="mt-8">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Tracking categories</h2>
          <p className="text-xs text-muted">Matched to the group standard by name. Confirm a category before its options.</p>
        </div>
        {isAdmin && rows.data.length > 0 && (
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => act(() => api.resuggestTracking(ws, entity))}>Re-suggest</Button>
            <Button onClick={() => act(() => api.confirmExactTracking(ws, entity))}>Confirm exact matches</Button>
          </div>
        )}
      </div>
      <ErrorNote message={error ?? rows.error} />
      {rows.data.length === 0 ? (
        <Card className="p-6 text-sm text-muted">{orgName} has no active tracking categories.</Card>
      ) : (
        <div className="space-y-4">
          {rows.data.map((c) => {
            const group = groups.find((g) => g.id === c.group_category?.id);
            const confirmed = c.mapping?.status === "confirmed" && !!c.group_category;
            return (
              <Card key={c.id} className="divide-y divide-border">
                <Line name={c.name} target={c.group_category?.name} mapping={c.mapping} choices={groups} canEdit={isAdmin}
                  decide={c.mapping ? decide("categories", c.mapping) : undefined}
                  proposals={canPropose ? [
                    ...(confirmed && c.group_category!.name !== c.name ? [{
                      label: `Propose renaming to “${c.group_category!.name}”`,
                      run: () => propose(`Rename tracking category ${c.name} in ${orgName}`,
                        { operation: "update_tracking_category", entity_tracking_category_id: c.id,
                          payload: { name: c.group_category!.name } }),
                    }] : []),
                    { label: "Propose archiving", run: () => propose(`Archive tracking category ${c.name} in ${orgName}`,
                      { operation: "archive_tracking_category", entity_tracking_category_id: c.id }) },
                  ] : []} />
                {c.options.map((o) => (
                  <div key={o.id} className="pl-6">
                    <Line name={o.name} target={o.group_option?.name} mapping={o.mapping} canEdit={isAdmin && confirmed}
                      choices={(group as TrackingCategory | undefined)?.options.filter((x) => x.status === "active") ?? []}
                      decide={o.mapping ? decide("options", o.mapping) : undefined}
                      proposals={canPropose ? [
                        ...(o.mapping?.status === "confirmed" && o.group_option && o.group_option.name !== o.name ? [{
                          label: `Propose renaming to “${o.group_option.name}”`,
                          run: () => propose(`Rename ${o.name} in ${c.name}, ${orgName}`,
                            { operation: "update_tracking_option", entity_tracking_option_id: o.id,
                              payload: { name: o.group_option!.name } }),
                        }] : []),
                        { label: "Propose archiving", run: () => propose(`Archive ${o.name} in ${c.name}, ${orgName}`,
                          { operation: "archive_tracking_option", entity_tracking_option_id: o.id }) },
                      ] : []} />
                  </div>
                ))}
              </Card>
            );
          })}
        </div>
      )}
    </section>
  );
}

function Line({ name, target, mapping, choices, canEdit, decide, proposals }: {
  name: string;
  target?: string;
  mapping: Mapping;
  choices: Choice[];
  canEdit: boolean;
  decide?: (action: "confirm" | "reject" | "assign", groupId?: string | null) => void;
  proposals: { label: string; run: () => void }[];
}) {
  const [assigning, setAssigning] = useState(false);
  const [choice, setChoice] = useState("");
  const unmatched = mapping?.source === "unmatched" && mapping.status !== "confirmed";
  const shown = target ?? (unmatched ? "Needs a group match" : mapping?.status === "confirmed" ? "Local only" : "—");

  return (
    <div className="grid gap-2 px-4 py-2.5 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto] md:items-start">
      <p className="text-sm font-medium text-slate-900">{name}</p>
      <div className="space-y-1">
        <p className="text-sm"><span className="text-muted">→</span> <b>{shown}</b></p>
        {mapping && (
          <div className="flex flex-wrap gap-1.5">
            <SourceBadge source={mapping.source} />
            {mapping.status === "confirmed" && <Badge tone="emerald">confirmed</Badge>}
            {mapping.status === "rejected" && <Badge tone="red">rejected</Badge>}
          </div>
        )}
        {mapping?.status !== "confirmed" && mapping?.reasoning && <p className="text-xs text-slate-600">{mapping.reasoning}</p>}
        {proposals.length > 0 && (
          <div className="flex flex-wrap gap-3 pt-0.5 text-xs">
            {proposals.map((p) => <button key={p.label} className="text-slate-600 underline" onClick={p.run}>{p.label}</button>)}
          </div>
        )}
      </div>
      {canEdit && decide && mapping && (
        <div className="flex flex-wrap items-center justify-end gap-1">
          {assigning ? (
            <>
              <select value={choice} onChange={(e) => setChoice(e.target.value)} aria-label={`Group match for ${name}`}
                className="max-w-56 rounded-lg border border-border-strong px-2 py-1.5 text-sm">
                <option value="">Choose…</option>
                <option value="local">Local only (no group equivalent)</option>
                {choices.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
              <Button disabled={!choice} onClick={() => { decide("assign", choice === "local" ? null : choice); setAssigning(false); }}>Save</Button>
              <Button variant="ghost" onClick={() => setAssigning(false)}>Cancel</Button>
            </>
          ) : (
            <>
              {mapping.status !== "confirmed" && !unmatched && <Button onClick={() => decide("confirm")}>Confirm</Button>}
              {mapping.status === "suggested" && !unmatched && <Button variant="ghost" onClick={() => decide("reject")}>Reject</Button>}
              <Button variant={unmatched ? "primary" : "ghost"} onClick={() => setAssigning(true)}>{unmatched ? "Choose…" : "Change…"}</Button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
