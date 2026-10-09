"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type ItemSpec } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { ActionBar, Button, Card, EmptyState, ErrorNote, GAP_CELL, Icon, Loading } from "@/components/ui";

type Cell = { state: keyof typeof GAP_CELL; entity_category_id: string | null };

// A selected gap: a whole category missing from an org, or one option missing
// from the org's (confirmed) category.
type Pick =
  | { kind: "category"; groupId: string; entityId: string }
  | { kind: "option"; groupId: string; entityId: string; entityCategoryId: string };

const keyOf = (p: Pick) => `${p.kind}:${p.groupId}:${p.entityId}`;

export function TrackingGaps({ ws, only, canPropose }: { ws: string; only: "gaps" | "all"; canPropose: boolean }) {
  const router = useRouter();
  const gaps = useData(() => api.trackingGaps(ws));
  const [picked, setPicked] = useState<Map<string, Pick>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!gaps.data) return <Loading />;
  const { entities, categories } = gaps.data;

  function toggle(p: Pick) {
    setPicked((prev) => {
      const next = new Map(prev);
      if (next.has(keyOf(p))) next.delete(keyOf(p));
      else next.set(keyOf(p), p);
      return next;
    });
  }

  async function propose() {
    setError(null);
    setBusy(true);
    try {
      const items: ItemSpec[] = [...picked.values()].map((p) => p.kind === "category"
        ? { operation: "create_tracking_category", entity_id: p.entityId, group_tracking_category_id: p.groupId }
        : { operation: "create_tracking_option", entity_id: p.entityId, entity_tracking_category_id: p.entityCategoryId,
            group_tracking_option_id: p.groupId });
      const change = await api.createChange(ws, `Fill ${items.length} tracking gap${items.length === 1 ? "" : "s"}`,
        items, "Create group tracking categories and options missing from these organisations.");
      router.push(`/w/${ws}/changes/${change.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const stale = new Set(entities.filter((e) => e.status !== "active").map((e) => e.id));

  function cell(c: Cell, p: Pick, label: string) {
    const style = GAP_CELL[c.state];
    const on = picked.has(keyOf(p));
    if (!(canPropose && c.state === "gap" && !stale.has(p.entityId))) {
      const title = c.state === "no_category" ? "The organisation doesn't have this category yet" : style.name;
      return <span title={title} className={`grid h-7 w-7 place-items-center rounded-lg text-xs font-semibold ${style.cls}`}>{style.label}</span>;
    }
    return (
      <button type="button" onClick={() => toggle(p)} aria-pressed={on} aria-label={label}
        title={on ? "Selected: will be proposed" : "Gap: select to create"}
        className={`grid h-7 w-7 place-items-center rounded-lg text-xs font-semibold transition ${on ? "bg-ink text-white ring-2 ring-brand ring-offset-1" : `${style.cls} hover:ring-2 hover:ring-red-300`}`}>
        {on ? <Icon name="check" size={14} /> : style.label}
      </button>
    );
  }

  const shown = categories.filter((c) => only === "all" || c.gaps > 0 || c.options.some((o) => o.gaps > 0));

  return (
    <section>
      <p className="mb-3 flex items-center gap-2 text-[13px] text-muted">
        <Icon name="info" size={15} /> A dash (–) means the organisation doesn&apos;t have the category yet, so its options can&apos;t be added until it does.
      </p>
      <ErrorNote message={error ?? gaps.error} />
      <Card className="canopy-scroll overflow-x-auto">
        {categories.length === 0 ? (
          <EmptyState icon="tag" title="No tracking categories in the standard">Add tracking categories to the group standard to see their gaps.</EmptyState>
        ) : shown.length === 0 ? (
          <EmptyState icon="check" title="No tracking gaps">Every category and option is covered.</EmptyState>
        ) : (
          <table className="w-full border-separate border-spacing-0 text-sm">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 min-w-64 border-b border-border bg-surface-sunken px-5 py-3 text-left"><span className="eyebrow">Category / option</span></th>
                {entities.map((e) => (
                  <th key={e.id} title={e.name} className="min-w-32 border-b border-border bg-surface-sunken px-3 py-3 text-left text-[13px] font-medium">
                    <span className="block max-w-36 truncate">{e.name}</span>
                    {e.status === "needs_reconnect" && (
                    <span title="Needs reconnecting: this organisation's data may be out of date"
                      className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-amber-700">
                      <Icon name="alert" size={12} /> Needs reconnecting
                    </span>
                  )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((c) => [
                <tr key={c.group_category.id} className="bg-surface-sunken/40">
                  <td className="sticky left-0 z-10 border-b border-border bg-surface-sunken/90 px-5 py-2.5 font-medium whitespace-nowrap">
                    <span className="flex items-center gap-2"><Icon name="tag" size={15} className="text-brand" />{c.group_category.name}</span>
                  </td>
                  {entities.map((e) => (
                    <td key={e.id} className="border-b border-border px-3 py-2.5">
                      {cell(c.cells[e.id] as Cell, { kind: "category", groupId: c.group_category.id, entityId: e.id },
                        `Create tracking category ${c.group_category.name} in ${e.name}`)}
                    </td>
                  ))}
                </tr>,
                ...c.options.filter((o) => only === "all" || o.gaps > 0).map((o) => (
                  <tr key={o.group_option.id}>
                    <td className="sticky left-0 z-10 border-b border-border bg-surface py-2.5 pl-12 pr-5 whitespace-nowrap text-foreground/80">{o.group_option.name}</td>
                    {entities.map((e) => {
                      const oc = o.cells[e.id] as Cell;
                      return (
                        <td key={e.id} className="border-b border-border px-3 py-2.5">
                          {cell(oc, { kind: "option", groupId: o.group_option.id, entityId: e.id,
                            entityCategoryId: oc.entity_category_id ?? "" },
                          `Add ${o.group_option.name} to ${c.group_category.name} in ${e.name}`)}
                        </td>
                      );
                    })}
                  </tr>
                )),
              ])}
            </tbody>
          </table>
        )}
      </Card>
      <ActionBar show={picked.size > 0}>
        <span><b className="tnum">{picked.size}</b> tracking {picked.size === 1 ? "gap" : "gaps"} selected</span>
        <button onClick={() => setPicked(new Map())} className="text-white/60 underline-offset-2 hover:text-white hover:underline">Clear</button>
        <Button variant="primary" size="sm" disabled={busy} onClick={propose}>Propose creating {picked.size === 1 ? "it" : "them"}</Button>
      </ActionBar>
    </section>
  );
}
