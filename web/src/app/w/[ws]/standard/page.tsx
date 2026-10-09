"use client";

import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { api, type GroupAccount } from "@/lib/api";
import { useRole } from "@/lib/session";
import { useData } from "@/lib/use-data";
import {
  Badge, Button, Card, Code, EmptyState, ErrorNote, Icon, Input, Loading, PageTitle, SearchInput, Select, SlideOver, Tabs,
} from "@/components/ui";
import { TrackingStandard } from "./tracking-standard";

const TYPES = ["REVENUE", "SALES", "OTHERINCOME", "DIRECTCOSTS", "EXPENSE", "OVERHEADS", "DEPRECIATN", "CURRENT", "FIXED",
  "INVENTORY", "NONCURRENT", "PREPAYMENT", "BANK", "CURRLIAB", "LIABILITY", "TERMLIAB", "EQUITY"];

type Section = "accounts" | "tracking";

const CLASS_STYLE: Record<string, string> = {
  ASSET: "bg-blue-50 text-blue-700 ring-blue-200",
  LIABILITY: "bg-amber-50 text-amber-800 ring-amber-200",
  EQUITY: "bg-violet-50 text-violet-700 ring-violet-200",
  REVENUE: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  EXPENSE: "bg-rose-50 text-rose-700 ring-rose-200",
};

export default function StandardPage() {
  const { ws } = useParams<{ ws: string }>();
  const { isAdmin } = useRole(ws);
  const standard = useData(() => api.standard(ws));
  const [section, setSection] = useState<Section>("accounts");
  const [query, setQuery] = useState("");
  const [cls, setCls] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rows = useMemo(() => standard.data ?? [], [standard.data]);
  const classes = useMemo(() => [...new Set(rows.map((g) => g.account_class))].sort(), [rows]);

  if (!standard.data) return <Loading />;

  async function run(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await standard.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const q = query.trim().toLowerCase();
  const shown = rows.filter((g) => (!cls || g.account_class === cls) && (!q || `${g.code} ${g.name} ${g.type}`.toLowerCase().includes(q)));
  const activeCount = rows.filter((g) => g.status === "active").length;

  return (
    <>
      <PageTitle
        title="Group standard"
        subtitle="The chart of accounts and tracking categories every organisation is mapped to. Orgs keep their own codes; Canopy records how each one lines up."
        action={isAdmin && rows.length > 0 && section === "accounts" && (
          <Button icon="plus" variant="dark" onClick={() => setAdding(true)}>Add account</Button>
        )}
      />
      <ErrorNote message={error ?? standard.error} />

      <Tabs<Section> value={section} onChange={setSection}
        options={[{ value: "accounts", label: "Accounts", icon: "layers", count: activeCount }, { value: "tracking", label: "Tracking categories", icon: "tag" }]} />

      <div className="mt-5">
        {section === "tracking" ? (
          <TrackingStandard ws={ws} isAdmin={isAdmin} />
        ) : rows.length === 0 ? (
          isAdmin ? <Seed ws={ws} run={run} /> : (
            <Card><EmptyState icon="layers" title="No group standard yet">An admin needs to set it up.</EmptyState></Card>
          )
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <SearchInput value={query} onChange={setQuery} label="Search the standard" placeholder="Search code, name or type…" className="w-full sm:w-72" />
              <Select value={cls} onChange={(e) => setCls(e.target.value)} aria-label="Filter by class" className="w-44">
                <option value="">All classes</option>
                {classes.map((c) => <option key={c} value={c}>{c[0] + c.slice(1).toLowerCase()}</option>)}
              </Select>
              <span className="ml-auto text-[13px] text-muted"><span className="tnum">{shown.length}</span> of <span className="tnum">{rows.length}</span></span>
            </div>
            <Card className="overflow-hidden">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-surface-sunken/60 text-left">
                  <tr>
                    <th className="eyebrow w-28 px-5 py-2.5 font-medium">Code</th>
                    <th className="eyebrow px-3 py-2.5 font-medium">Name</th>
                    <th className="eyebrow hidden px-3 py-2.5 font-medium sm:table-cell">Type</th>
                    <th className="eyebrow hidden px-3 py-2.5 font-medium md:table-cell">Class</th>
                    <th className="px-5 py-2.5" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {shown.map((g: GroupAccount) => (
                    <tr key={g.id} className={`transition hover:bg-surface-hover ${g.status === "archived" ? "text-muted" : ""}`}>
                      <td className="px-5 py-3"><Code>{g.code}</Code></td>
                      <td className="px-3 py-3">
                        <span className={g.status === "archived" ? "line-through decoration-border-strong" : "font-medium"}>{g.name}</span>{" "}
                        {g.status === "archived" && <Badge>Archived</Badge>}
                      </td>
                      <td className="hidden px-3 py-3 text-muted sm:table-cell">{g.type}</td>
                      <td className="hidden px-3 py-3 md:table-cell">
                        <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize ring-1 ring-inset ${CLASS_STYLE[g.account_class] ?? "bg-slate-100 text-slate-700 ring-slate-200"}`}>
                          {g.account_class.toLowerCase()}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-right">
                        {isAdmin && (
                          <Button variant="ghost" size="sm" icon={g.status === "archived" ? "refresh" : "archive"}
                            onClick={() => run(() => api.editGroupAccount(ws, g.id, { status: g.status === "archived" ? "active" : "archived" }))}>
                            {g.status === "archived" ? "Restore" : "Archive"}
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {shown.length === 0 && (
                    <tr><td colSpan={5}><EmptyState icon="search" title="No accounts match">Try a different search or class.</EmptyState></td></tr>
                  )}
                </tbody>
              </table>
            </Card>
          </>
        )}
      </div>

      {adding && <AddAccount onClose={() => setAdding(false)} run={(body) => run(() => api.addGroupAccount(ws, body))} />}
    </>
  );
}

function Seed({ ws, run }: { ws: string; run: (fn: () => Promise<unknown>) => Promise<void> }) {
  const entities = useData(() => api.entities(ws));
  const [entityId, setEntityId] = useState("");
  const synced = (entities.data ?? []).filter((e) => e.sync_status === "ok");

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card padded className="flex flex-col gap-4">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-soft text-brand-strong"><Icon name="building" size={20} /></span>
        <div>
          <h2 className="text-base font-semibold tracking-tight">Start from one organisation&apos;s chart</h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">Usually your lead or best-kept entity. Its coded, active accounts become the group standard, and you can edit it afterwards.</p>
        </div>
        {synced.length === 0 ? (
          <p className="rounded-lg bg-surface-sunken px-3 py-2.5 text-sm text-muted">No organisation has finished syncing yet.</p>
        ) : (
          <div className="mt-auto flex gap-2">
            <Select value={entityId} onChange={(e) => setEntityId(e.target.value)} aria-label="Organisation">
              <option value="">Choose an organisation…</option>
              {synced.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </Select>
            <Button disabled={!entityId} onClick={() => run(() => api.seedStandard(ws, entityId))}>Use this chart</Button>
          </div>
        )}
      </Card>
      <Card padded className="flex flex-col gap-4">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-50 text-blue-700"><Icon name="upload" size={20} /></span>
        <div>
          <h2 className="text-base font-semibold tracking-tight">Import a CSV</h2>
          <p className="mt-1.5 text-sm leading-relaxed text-muted">
            Columns <code className="rounded bg-surface-sunken px-1 font-mono text-xs">code,name,type</code> (Xero account types), optionally <code className="rounded bg-surface-sunken px-1 font-mono text-xs">description</code>.
          </p>
        </div>
        <label className="mt-auto flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-border-strong bg-surface-sunken/50 px-4 py-5 text-sm font-medium text-muted transition hover:border-brand hover:bg-brand-soft/50 hover:text-brand-strong">
          <Icon name="file" size={18} /> Choose a CSV file
          <input type="file" accept=".csv,text/csv" aria-label="Group standard CSV" className="sr-only"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) run(() => api.importStandard(ws, f)); }} />
        </label>
      </Card>
    </div>
  );
}

function AddAccount({ run, onClose }: { run: (body: { code: string; name: string; type: string }) => Promise<void>; onClose: () => void }) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [type, setType] = useState("EXPENSE");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    await run({ code, name, type });
    setBusy(false);
    onClose();
  }

  return (
    <SlideOver open onClose={onClose} title="Add a group account" description="It becomes part of the standard every organisation is mapped to."
      footer={<div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button type="submit" form="add-account" disabled={busy || !code.trim() || !name.trim()}>Add account</Button></div>}>
      <form id="add-account" onSubmit={submit} className="space-y-5 p-5">
        <div>
          <label htmlFor="ga-code" className="mb-1.5 block text-sm font-medium">Code</label>
          <Input id="ga-code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="e.g. 200" required autoFocus />
        </div>
        <div>
          <label htmlFor="ga-name" className="mb-1.5 block text-sm font-medium">Account name</label>
          <Input id="ga-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sales" required />
        </div>
        <div>
          <label htmlFor="ga-type" className="mb-1.5 block text-sm font-medium">Type</label>
          <Select id="ga-type" value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => <option key={t}>{t}</option>)}
          </Select>
          <p className="mt-1.5 text-xs text-muted">Xero account types decide which class (revenue, expense…) the account belongs to.</p>
        </div>
      </form>
    </SlideOver>
  );
}
