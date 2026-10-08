"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { api, type GroupAccount } from "@/lib/api";
import { useRole } from "@/lib/session";
import { useData } from "@/lib/use-data";
import { Badge, Button, Card, ErrorNote, Loading, PageTitle } from "@/components/ui";
import { TrackingStandard } from "./tracking-standard";

const TYPES = ["REVENUE", "SALES", "OTHERINCOME", "DIRECTCOSTS", "EXPENSE", "OVERHEADS", "DEPRECIATN", "CURRENT", "FIXED",
  "INVENTORY", "NONCURRENT", "PREPAYMENT", "BANK", "CURRLIAB", "LIABILITY", "TERMLIAB", "EQUITY"];

export default function StandardPage() {
  const { ws } = useParams<{ ws: string }>();
  const { isAdmin } = useRole(ws);
  const standard = useData(() => api.standard(ws));
  const [error, setError] = useState<string | null>(null);

  if (!standard.data) return <Loading />;
  const rows = standard.data;

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
    <>
      <PageTitle title="Group standard" subtitle="The chart of accounts and tracking categories every organisation is mapped to. Orgs keep their own codes; Canopy records how each one lines up." />
      <ErrorNote message={error ?? standard.error} />
      {rows.length === 0 ? (
        isAdmin ? <Seed ws={ws} run={run} /> : <Card className="p-6 text-sm text-muted">No group standard yet. An admin sets it up.</Card>
      ) : (
        <>
          {isAdmin && <AddAccount run={(body) => run(() => api.addGroupAccount(ws, body))} />}
          <Card className="mt-4 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-surface-sunken text-left text-xs uppercase tracking-wide text-muted">
                <tr><th className="px-4 py-2">Code</th><th className="px-4 py-2">Name</th><th className="px-4 py-2">Type</th><th className="px-4 py-2">Class</th><th className="px-4 py-2" /></tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((g: GroupAccount) => (
                  <tr key={g.id} className={g.status === "archived" ? "text-muted" : ""}>
                    <td className="px-4 py-2 font-mono">{g.code}</td>
                    <td className="px-4 py-2">{g.name} {g.status === "archived" && <Badge>archived</Badge>}</td>
                    <td className="px-4 py-2">{g.type}</td>
                    <td className="px-4 py-2">{g.account_class}</td>
                    <td className="px-4 py-2 text-right">
                      {isAdmin && (
                        <Button variant="ghost" onClick={() => run(() => api.editGroupAccount(ws, g.id, { status: g.status === "archived" ? "active" : "archived" }))}>
                          {g.status === "archived" ? "Restore" : "Archive"}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
      <TrackingStandard ws={ws} isAdmin={isAdmin} />
    </>
  );
}

function Seed({ ws, run }: { ws: string; run: (fn: () => Promise<unknown>) => Promise<void> }) {
  const entities = useData(() => api.entities(ws));
  const [entityId, setEntityId] = useState("");
  const synced = (entities.data ?? []).filter((e) => e.sync_status === "ok");

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className="space-y-3 p-5">
        <h2 className="text-sm font-semibold text-slate-900">Start from one organisation&apos;s chart</h2>
        <p className="text-sm text-muted">Usually your lead or best-kept entity. Its coded, active accounts become the group standard; you can edit it afterwards.</p>
        {synced.length === 0 ? (
          <p className="text-sm text-muted">No organisation has finished syncing yet.</p>
        ) : (
          <div className="flex gap-2">
            <select value={entityId} onChange={(e) => setEntityId(e.target.value)} className="flex-1 rounded-lg border border-border-strong px-3 py-2 text-sm" aria-label="Organisation">
              <option value="">Choose an organisation…</option>
              {synced.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </select>
            <Button disabled={!entityId} onClick={() => run(() => api.seedStandard(ws, entityId))}>Use this chart</Button>
          </div>
        )}
      </Card>
      <Card className="space-y-3 p-5">
        <h2 className="text-sm font-semibold text-slate-900">Import a CSV</h2>
        <p className="text-sm text-muted">Columns <code className="font-mono">code,name,type</code> (Xero account types), optionally <code className="font-mono">description</code>.</p>
        <input type="file" accept=".csv,text/csv" aria-label="Group standard CSV"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => api.importStandard(ws, f)); }}
          className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-900 file:px-3 file:py-2 file:text-white" />
      </Card>
    </div>
  );
}

function AddAccount({ run }: { run: (body: { code: string; name: string; type: string }) => Promise<void> }) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState("EXPENSE");
  return (
    <Card className="p-4">
      <form className="flex flex-wrap items-end gap-2" onSubmit={async (e) => { e.preventDefault(); await run({ code, name, type }); setCode(""); setName(""); }}>
        <input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Code" aria-label="Code" className="w-24 rounded-lg border border-border-strong px-3 py-2 text-sm" required />
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Account name" aria-label="Account name" className="min-w-48 flex-1 rounded-lg border border-border-strong px-3 py-2 text-sm" required />
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Type" className="rounded-lg border border-border-strong px-3 py-2 text-sm">
          {TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
        <Button type="submit">Add account</Button>
      </form>
    </Card>
  );
}
