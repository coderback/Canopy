"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { api, exportUrl } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Card, ErrorNote, Loading, PageTitle, Segmented } from "@/components/ui";

const CELL = {
  mapped: { cls: "bg-emerald-100 text-emerald-800", label: "✓" },
  pending: { cls: "bg-amber-100 text-amber-800", label: "?" },
  gap: { cls: "bg-red-100 text-red-800", label: "✕" },
} as const;

export default function GapsPage() {
  const { ws } = useParams<{ ws: string }>();
  const gaps = useData(() => api.gaps(ws));
  const [only, setOnly] = useState<"gaps" | "all">("gaps");

  if (!gaps.data) return <Loading />;
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
      <ErrorNote message={gaps.error} />
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
                    return (
                      <td key={e.id} className="px-3 py-2 text-center">
                        <span title={c.state} className={`inline-flex h-6 w-6 items-center justify-center rounded ${style.cls}`}>{style.label}</span>
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
