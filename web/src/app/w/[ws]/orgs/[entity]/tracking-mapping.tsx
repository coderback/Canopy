"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type ItemSpec, type TrackingCategory, type TrackingRow } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Button, Card, EmptyState, ErrorNote, Icon, Loading, Menu, SourceBadge } from "@/components/ui";
import { GroupPicker, type PickerChoice } from "@/components/group-picker";

type Mapping = TrackingRow["mapping"];

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
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13px] text-muted">Matched to the group standard by name. Confirm a category before its options.</p>
        {isAdmin && rows.data.length > 0 && (
          <div className="flex gap-2">
            <Button variant="outline" icon="refresh" onClick={() => act(() => api.resuggestTracking(ws, entity))}>Re-suggest</Button>
            <Button icon="check" onClick={() => act(() => api.confirmExactTracking(ws, entity))}>Confirm exact matches</Button>
          </div>
        )}
      </div>
      <ErrorNote message={error ?? rows.error} />
      {rows.data.length === 0 ? (
        <Card><EmptyState icon="tag" title="No tracking categories">{orgName} has no active tracking categories.</EmptyState></Card>
      ) : (
        <div className="space-y-4">
          {rows.data.map((c) => {
            const group = groups.find((g) => g.id === c.group_category?.id);
            const confirmed = c.mapping?.status === "confirmed" && !!c.group_category;
            return (
              <Card key={c.id} className="overflow-hidden">
                <div className="bg-surface-sunken/50">
                  <Line kind="Category" name={c.name} target={c.group_category?.name} targetId={c.group_category?.id} mapping={c.mapping}
                    choices={groups.map((g) => ({ id: g.id, name: g.name }))} canEdit={isAdmin}
                    decide={c.mapping ? decide("categories", c.mapping) : undefined}
                    proposals={canPropose ? [
                      ...(confirmed && c.group_category!.name !== c.name ? [{
                        label: `Propose renaming to “${c.group_category!.name}”`,
                        run: () => propose(`Rename tracking category ${c.name} in ${orgName}`,
                          { operation: "update_tracking_category", entity_tracking_category_id: c.id,
                            payload: { name: c.group_category!.name } }),
                      }] : []),
                      { label: "Propose archiving this category", danger: true, run: () => propose(`Archive tracking category ${c.name} in ${orgName}`,
                        { operation: "archive_tracking_category", entity_tracking_category_id: c.id }) },
                    ] : []} />
                </div>
                {c.options.length > 0 && (
                  <ul className="divide-y divide-border border-t border-border">
                    {c.options.map((o) => (
                      <li key={o.id} className="pl-7">
                        <Line kind="Option" name={o.name} target={o.group_option?.name} targetId={o.group_option?.id} mapping={o.mapping} canEdit={isAdmin && confirmed}
                          choices={((group as TrackingCategory | undefined)?.options.filter((x) => x.status === "active") ?? [])
                            .map((x) => ({ id: x.id, name: x.name }))}
                          decide={o.mapping ? decide("options", o.mapping) : undefined}
                          proposals={canPropose ? [
                            ...(o.mapping?.status === "confirmed" && o.group_option && o.group_option.name !== o.name ? [{
                              label: `Propose renaming to “${o.group_option.name}”`,
                              run: () => propose(`Rename ${o.name} in ${c.name}, ${orgName}`,
                                { operation: "update_tracking_option", entity_tracking_option_id: o.id,
                                  payload: { name: o.group_option!.name } }),
                            }] : []),
                            { label: "Propose archiving this option", danger: true, run: () => propose(`Archive ${o.name} in ${c.name}, ${orgName}`,
                              { operation: "archive_tracking_option", entity_tracking_option_id: o.id }) },
                          ] : []} />
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </section>
  );
}

function Line({ kind, name, target, targetId, mapping, choices, canEdit, decide, proposals }: {
  kind: "Category" | "Option";
  name: string;
  target?: string;
  targetId?: string;
  mapping: Mapping;
  choices: PickerChoice[];
  canEdit: boolean;
  decide?: (action: "confirm" | "reject" | "assign", groupId?: string | null) => void;
  proposals: { label: string; run: () => void; danger?: boolean }[];
}) {
  const [assigning, setAssigning] = useState(false);
  const unmatched = mapping?.source === "unmatched" && mapping.status !== "confirmed";
  const confirmed = mapping?.status === "confirmed";
  const shown = target ?? (unmatched ? "Needs a group match" : confirmed ? "Local only" : "—");

  return (
    <div className="grid gap-x-4 gap-y-2 px-5 py-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_232px] md:items-center">
      <p className="flex items-center gap-2 text-sm font-medium">
        {kind === "Category" && <Icon name="tag" size={15} className="text-brand" />}
        {name}
      </p>
      <div className="min-w-0 space-y-1">
        <p className="flex items-center gap-2 text-sm">
          <Icon name="arrowRight" size={15} className={unmatched ? "text-amber-500" : "text-brand"} />
          <span className={unmatched ? "font-medium text-amber-700" : target ? "font-medium" : "text-muted"}>{shown}</span>
        </p>
        {mapping && (
          <div className="flex flex-wrap items-center gap-1.5 pl-[23px]">
            <SourceBadge source={mapping.source} />
            {confirmed && <Badge tone="emerald" dot>Confirmed</Badge>}
            {mapping.status === "rejected" && <Badge tone="red" dot>Rejected</Badge>}
          </div>
        )}
        {!confirmed && mapping?.reasoning && <p className="pl-[23px] text-xs leading-relaxed text-muted">{mapping.reasoning}</p>}
      </div>
      <div className="flex items-center gap-1.5 md:justify-end">
        {canEdit && decide && mapping && (
          <>
            {!confirmed && !unmatched && <Button size="sm" icon="check" onClick={() => decide("confirm")}>Confirm</Button>}
            {mapping.status === "suggested" && !unmatched && <Button size="sm" variant="ghost" onClick={() => decide("reject")}>Reject</Button>}
            <Button size="sm" variant={unmatched ? "primary" : "outline"} onClick={() => setAssigning(true)}>{unmatched ? "Choose…" : "Change"}</Button>
          </>
        )}
        <Menu items={proposals.map((p) => ({ label: p.label, onClick: p.run, danger: p.danger, icon: p.danger ? "archive" as const : "edit" as const }))} />
      </div>
      {assigning && (
        <GroupPicker open onClose={() => setAssigning(false)} title={`Choose a group ${kind.toLowerCase()}`}
          subject={<>Mapping <b className="text-foreground">{name}</b></>} noun={`group ${kind.toLowerCase()}`}
          choices={choices} current={confirmed ? (targetId ?? null) : undefined}
          onSave={(id) => decide?.("assign", id)} />
      )}
    </div>
  );
}
