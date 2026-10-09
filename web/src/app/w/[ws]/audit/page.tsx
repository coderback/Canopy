"use client";

import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Avatar, Card, EmptyState, ErrorNote, Icon, Loading, PageTitle } from "@/components/ui";

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
      <Card className="overflow-hidden">
        {audit.data.length === 0 ? (
          <EmptyState icon="log" title="Nothing yet">Actions in this workspace will be recorded here.</EmptyState>
        ) : (
          <ul className="divide-y divide-border">
            {audit.data.map((e) => {
              const actor = e.actor_user_id ? who.get(e.actor_user_id) ?? "Former member" : "System";
              const hasDetail = !!(e.before || e.after);
              return (
                <li key={e.id}>
                  <details className="group">
                    <summary className={`flex list-none items-center gap-3 px-5 py-3 text-sm transition ${hasDetail ? "cursor-pointer hover:bg-surface-hover" : "cursor-default"}`}>
                      {e.actor_user_id ? <Avatar name={actor} size={28} /> : (
                        <span className="grid h-7 w-7 place-items-center rounded-full bg-surface-sunken text-muted ring-1 ring-inset ring-border"><Icon name="settings" size={14} /></span>
                      )}
                      <span className="min-w-0 flex-1">
                        <span className="font-medium">{e.action}</span>
                        <span className="ml-2 text-muted">by {actor}</span>
                      </span>
                      <time className="tnum shrink-0 font-mono text-xs text-subtle" dateTime={e.at}>{new Date(e.at).toLocaleString()}</time>
                      {hasDetail && <Icon name="chevronRight" size={16} className="shrink-0 text-subtle transition group-open:rotate-90" />}
                    </summary>
                    {hasDetail && (
                      <div className="grid gap-2 border-t border-border bg-surface-sunken/50 px-5 py-3 sm:grid-cols-2">
                        {(["before", "after"] as const).map((k) => (
                          <div key={k} className="rounded-lg border border-border bg-surface">
                            <p className="eyebrow border-b border-border px-3 py-1.5">{k}</p>
                            <pre className="overflow-x-auto px-3 py-2 font-mono text-[11px] leading-relaxed">{e[k] ? JSON.stringify(e[k], null, 2) : "—"}</pre>
                          </div>
                        ))}
                      </div>
                    )}
                  </details>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </>
  );
}
