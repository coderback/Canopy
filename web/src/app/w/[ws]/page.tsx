"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { api, connectUrl, type Entity, type GroupAccount } from "@/lib/api";
import { useRole } from "@/lib/session";
import { useData } from "@/lib/use-data";
import { Button, Card, ErrorNote, Loading, PageTitle, SyncBadge } from "@/components/ui";

const BUSY = new Set(["queued", "running"]);

export default function Overview() {
  const { ws } = useParams<{ ws: string }>();
  const { isAdmin } = useRole(ws);
  const entities = useData(() => api.entities(ws), (list: Entity[]) => list.some((e) => BUSY.has(e.sync_status)));
  const standard = useData(() => api.standard(ws));
  const toReview = useData(() => api.changes(ws, true));

  if (!entities.data || !standard.data) return <Loading />;
  const orgs = entities.data;

  async function sync(e: Entity) {
    try {
      await api.syncEntity(ws, e.id);
      await entities.reload();
    } catch (err) {
      entities.setError((err as Error).message);
    }
  }

  return (
    <>
      <PageTitle
        title="Organisations"
        subtitle="Each connected Xero organisation, its sync status, and how its chart maps to the group standard."
        action={isAdmin && <a href={connectUrl(ws)} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">Connect Xero organisations</a>}
      />
      <ErrorNote message={entities.error} />
      {!!toReview.data?.length && (
        <Card className="mb-4 flex flex-wrap items-center justify-between gap-2 border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <span>
            {toReview.data.length} self-approved {toReview.data.length === 1 ? "change is" : "changes are"} waiting for
            someone else to review {toReview.data.length === 1 ? "it" : "them"}.
          </span>
          <Link href={`/w/${ws}/changes?review=1`} className="font-medium underline">Review queue →</Link>
        </Card>
      )}
      <Setup orgs={orgs} standard={standard.data} ws={ws} />
      <Card className="mt-4 overflow-hidden">
        {orgs.length === 0 ? (
          <p className="p-6 text-sm text-muted">No organisations connected yet. Connecting is read-only: Canopy can see charts of accounts but can&apos;t change anything in Xero.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-surface-sunken text-left text-xs uppercase tracking-wide text-muted">
              <tr><th className="px-4 py-2">Organisation</th><th className="px-4 py-2">Sync</th><th className="px-4 py-2">Last synced</th><th className="px-4 py-2" /></tr>
            </thead>
            <tbody className="divide-y divide-border">
              {orgs.map((e) => (
                <tr key={e.id}>
                  <td className="px-4 py-3 font-medium text-slate-900">{e.name}</td>
                  <td className="px-4 py-3">
                    <SyncBadge status={e.sync_status} />
                    {e.sync_error && <p className="mt-1 max-w-md text-xs text-red-700">{e.sync_error}</p>}
                  </td>
                  <td className="px-4 py-3 text-muted">{e.last_synced_at ? new Date(e.last_synced_at).toLocaleString() : "—"}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      {isAdmin && <Button variant="ghost" onClick={() => sync(e)} disabled={BUSY.has(e.sync_status)}>Sync now</Button>}
                      <Link href={`/w/${ws}/orgs/${e.id}`} className="rounded-lg px-4 py-2 text-sm font-medium text-brand-strong hover:bg-emerald-50">Review mapping →</Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}

function Setup({ orgs, standard, ws }: { orgs: Entity[]; standard: GroupAccount[]; ws: string }) {
  const steps = [
    { done: orgs.length > 0, label: "Connect your Xero organisations (read-only)" },
    { done: orgs.some((e) => e.sync_status === "ok"), label: "Wait for the first sync of their charts of accounts" },
    { done: standard.length > 0, label: <>Set up the <Link className="underline" href={`/w/${ws}/standard`}>group standard</Link> from one org&apos;s chart or a CSV</> },
    { done: false, label: <>Review each org&apos;s suggested mapping, then check the <Link className="underline" href={`/w/${ws}/gaps`}>gaps</Link></> },
  ];
  if (steps.slice(0, 3).every((s) => s.done)) return null;
  return (
    <Card className="p-4">
      <p className="mb-2 text-sm font-medium text-slate-900">Getting started</p>
      <ol className="space-y-1 text-sm">
        {steps.map((s, i) => (
          <li key={i} className={s.done ? "text-muted line-through" : "text-slate-700"}>
            {s.done ? "✓" : `${i + 1}.`} {s.label}
          </li>
        ))}
      </ol>
    </Card>
  );
}
