"use client";

import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Card, ErrorNote, Loading, PageTitle } from "@/components/ui";

export default function AuditPage() {
  const { ws } = useParams<{ ws: string }>();
  const audit = useData(() => api.audit(ws));
  const members = useData(() => api.members(ws));

  if (!audit.data) return <Loading />;
  const who = new Map((members.data ?? []).map((m) => [m.user_id, m.name || m.email]));

  return (
    <>
      <PageTitle title="Audit log" subtitle="Every change in this workspace: who, what, and the before/after. Append-only." />
      <ErrorNote message={audit.error} />
      <Card className="divide-y divide-border">
        {audit.data.length === 0 && <p className="p-6 text-sm text-muted">Nothing yet.</p>}
        {audit.data.map((e) => (
          <details key={e.id} className="px-4 py-2 text-sm">
            <summary className="flex cursor-pointer flex-wrap gap-x-3">
              <span className="font-mono text-xs text-muted">{new Date(e.at).toLocaleString()}</span>
              <span className="font-medium text-slate-900">{e.action}</span>
              <span className="text-muted">{e.actor_user_id ? who.get(e.actor_user_id) ?? "former member" : "system"}</span>
            </summary>
            {(e.before || e.after) && (
              <pre className="mt-2 overflow-x-auto rounded bg-surface-sunken p-2 font-mono text-xs">{JSON.stringify({ before: e.before, after: e.after }, null, 2)}</pre>
            )}
          </details>
        ))}
      </Card>
    </>
  );
}
