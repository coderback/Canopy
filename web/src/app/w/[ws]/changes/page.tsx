"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Card, ChangeBadge, ErrorNote, Loading, PageTitle } from "@/components/ui";

export default function ChangesPage() {
  const { ws } = useParams<{ ws: string }>();
  const changes = useData(() => api.changes(ws), (list) => list.some((c) => c.status === "executing"));

  if (!changes.data) return <Loading />;

  return (
    <>
      <PageTitle title="Changes" subtitle="Proposed, approved and applied changes to your Xero organisations. Start one from the Gaps page or an organisation's mapping." />
      <ErrorNote message={changes.error} />
      <Card className="divide-y divide-border">
        {changes.data.length === 0 && <p className="p-6 text-sm text-muted">No changes yet.</p>}
        {changes.data.map((c) => {
          const total = Object.values(c.item_counts).reduce((a, b) => a + b, 0);
          return (
            <Link key={c.id} href={`/w/${ws}/changes/${c.id}`} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm hover:bg-surface-sunken">
              <ChangeBadge status={c.status} />
              <span className="flex-1 font-medium text-slate-900">{c.title}</span>
              <span className="text-muted">{total} {total === 1 ? "org" : "orgs"} · by {c.author.name || c.author.email}</span>
              <span className="text-muted">{new Date(c.created_at).toLocaleDateString()}</span>
            </Link>
          );
        })}
      </Card>
    </>
  );
}
