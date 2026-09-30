"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { api, exportUrl } from "@/lib/api";
import { useRole } from "@/lib/session";
import { useData } from "@/lib/use-data";
import { Button, Card, ErrorNote, Loading, PageTitle, Segmented } from "@/components/ui";

const CELL = {
  mapped: { cls: "bg-emerald-100 text-emerald-800", label: "✓" },
  pending: { cls: "bg-amber-100 text-amber-800", label: "?" },
  gap: { cls: "bg-red-100 text-red-800", label: "✕" },
} as const;

export default function GapsPage() {
  const { ws } = useParams<{ ws: string }>();
  const router = useRouter();
  const { role } = useRole(ws);
  const gaps = useData(() => api.gaps(ws));
  const settings = useData(() => api.settings(ws));
  const [only, setOnly] = useState<"gaps" | "all">("gaps");
  // Selected gaps to fix, as "groupAccountId:entityId".
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  if (!gaps.data || !settings.data) return <Loading />;
  const canPropose = settings.data.changes_enabled && ["owner", "admin", "preparer"].includes(role ?? "");

  function toggle(key: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function propose() {
    setError(null);
    try {
      const items = [...picked].map((key) => {
        const [groupId, entityId] = key.split(":");
        return { operation: "create_account" as const, entity_id: entityId, group_account_id: groupId };
      });
      const change = await api.createChange(ws, `Fill ${items.length} gap${items.length === 1 ? "" : "s"}`, items,
        "Create group accounts missing from these organisations.");
      router.push(`/w/${ws}/changes/${change.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  }
  const { entities, rows } = gaps.data;
  const shown = only === "gaps" ? rows.filter((r) => r.gaps > 0) : rows;
  const totalGaps = rows.reduce((n, r) => n + r.gaps, 0);

  return (
    <>
      <PageTitle
        title="Gaps"
        subtitle={`Group accounts with no confirmed mapping in an organisation. ${totalGaps} gap${totalGaps === 1 ? "" : "s"} across ${entities.length} organisations.`}
        action={<a href={exportUrl(ws)} className="rounded-lg border border-border-strong bg-surface px-4 py-2 text-sm font-medium text-slate-800 hover:bg-surface-sunken">Export mapping (CSV)</a>}
      />
      <ErrorNote message={error ?? gaps.error} />
      {canPropose && (
        <div className="mb-3 flex items-center gap-3 text-sm">
          <span className="text-muted">Select ✕ cells to create those accounts in Xero.</span>
          <Button disabled={picked.size === 0} onClick={propose}>
            Propose creating {picked.size} account{picked.size === 1 ? "" : "s"}
          </Button>
        </div>
      )}
      <div className="mb-3 flex flex-wrap items-center gap-4">
        <div className="w-56"><Segmented value={only} onChange={setOnly} options={[{ value: "gaps", label: "Only gaps" }, { value: "all", label: "Everything" }]} /></div>
        <p className="text-xs text-muted">✓ mapped · ? suggested, awaiting review · ✕ gap</p>
      </div>
      <Card className="canopy-scroll overflow-x-auto">
        {rows.length === 0 ? (
          <p className="p-6 text-sm text-muted">Set up the group standard to see gaps.</p>
        ) : (
          <table className="text-sm">
            <thead className="bg-surface-sunken text-left text-xs text-muted">
              <tr>
                <th className="sticky left-0 bg-surface-sunken px-4 py-2">Group account</th>
                {entities.map((e) => (
                  <th key={e.id} className="px-3 py-2 font-medium"><Link className="hover:underline" href={`/w/${ws}/orgs/${e.id}`}>{e.name}</Link></th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {shown.map((r) => (
                <tr key={r.group_account.id}>
                  <td className="sticky left-0 bg-surface px-4 py-2 whitespace-nowrap"><span className="font-mono text-muted">{r.group_account.code}</span> {r.group_account.name}</td>
                  {entities.map((e) => {
                    const c = r.cells[e.id];
                    const style = CELL[c.state];
                    const key = `${r.group_account.id}:${e.id}`;
                    const selectable = canPropose && c.state === "gap";
                    const on = picked.has(key);
                    return (
                      <td key={e.id} className="px-3 py-2 text-center">
                        {selectable ? (
                          <button type="button" onClick={() => toggle(key)} aria-pressed={on}
                            title={on ? "Selected: will be proposed" : "Gap: select to create"}
                            aria-label={`Create ${r.group_account.code} ${r.group_account.name} in ${e.name}`}
                            className={`inline-flex h-6 w-6 items-center justify-center rounded ${on ? "bg-emerald-600 text-white ring-2 ring-emerald-300" : style.cls}`}>
                            {on ? "+" : style.label}
                          </button>
                        ) : (
                          <span title={c.state} className={`inline-flex h-6 w-6 items-center justify-center rounded ${style.cls}`}>{style.label}</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
