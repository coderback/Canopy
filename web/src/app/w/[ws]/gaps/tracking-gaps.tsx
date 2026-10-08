"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type ItemSpec } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Button, Card, ErrorNote, GAP_CELL, Loading } from "@/components/ui";

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
    }
  }

  function cell(c: Cell, p: Pick, label: string) {
    const style = GAP_CELL[c.state];
    const on = picked.has(keyOf(p));
    if (!(canPropose && c.state === "gap")) {
      const title = c.state === "no_category" ? "The organisation doesn't have this category yet" : c.state;
      return <span title={title} className={`inline-flex h-6 w-6 items-center justify-center rounded ${style.cls}`}>{style.label}</span>;
    }
    return (
      <button type="button" onClick={() => toggle(p)} aria-pressed={on} aria-label={label}
        title={on ? "Selected: will be proposed" : "Gap: select to create"}
        className={`inline-flex h-6 w-6 items-center justify-center rounded ${on ? "bg-emerald-600 text-white ring-2 ring-emerald-300" : style.cls}`}>
        {on ? "+" : style.label}
      </button>
    );
  }

  const shown = categories.filter((c) => only === "all" || c.gaps > 0 || c.options.some((o) => o.gaps > 0));

  return (
    <section className="mt-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Tracking categories</h2>
          <p className="text-xs text-muted">– means the organisation doesn&apos;t have the category yet, so its options can&apos;t be added until it does.</p>
        </div>
        {canPropose && (
          <Button disabled={picked.size === 0} onClick={propose}>
            Propose {picked.size} tracking change{picked.size === 1 ? "" : "s"}
          </Button>
        )}
      </div>
      <ErrorNote message={error ?? gaps.error} />
      <Card className="canopy-scroll overflow-x-auto">
        {categories.length === 0 ? (
          <p className="p-6 text-sm text-muted">Add tracking categories to the group standard to see their gaps.</p>
        ) : shown.length === 0 ? (
          <p className="p-6 text-sm text-muted">No tracking gaps.</p>
        ) : (
          <table className="text-sm">
            <thead className="bg-surface-sunken text-left text-xs text-muted">
              <tr>
                <th className="sticky left-0 bg-surface-sunken px-4 py-2">Category / option</th>
                {entities.map((e) => <th key={e.id} className="px-3 py-2 font-medium">{e.name}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {shown.map((c) => [
                <tr key={c.group_category.id} className="bg-surface-sunken/40">
                  <td className="sticky left-0 bg-surface px-4 py-2 font-medium whitespace-nowrap">{c.group_category.name}</td>
                  {entities.map((e) => (
                    <td key={e.id} className="px-3 py-2 text-center">
                      {cell(c.cells[e.id] as Cell, { kind: "category", groupId: c.group_category.id, entityId: e.id },
                        `Create tracking category ${c.group_category.name} in ${e.name}`)}
                    </td>
                  ))}
                </tr>,
                ...c.options.filter((o) => only === "all" || o.gaps > 0).map((o) => (
                  <tr key={o.group_option.id}>
                    <td className="sticky left-0 bg-surface py-2 pl-8 pr-4 whitespace-nowrap text-slate-700">{o.group_option.name}</td>
                    {entities.map((e) => {
                      const oc = o.cells[e.id] as Cell;
                      return (
                        <td key={e.id} className="px-3 py-2 text-center">
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
    </section>
  );
}
