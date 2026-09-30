"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Badge, Card, ChangeBadge, ErrorNote, Loading, PageTitle, Segmented } from "@/components/ui";

type Filter = "all" | "review";

export default function ChangesPage() {
  return (
    <Suspense fallback={<Loading />}>
      <Changes />
    </Suspense>
  );
}

function Changes() {
  const { ws } = useParams<{ ws: string }>();
  const [filter, setFilter] = useState<Filter>(useSearchParams().get("review") ? "review" : "all");
  const changes = useData(() => api.changes(ws), (list) => list.some((c) => c.status === "executing"));

  if (!changes.data) return <Loading />;
  const toReview = changes.data.filter((c) => c.needs_review);
  const shown = filter === "review" ? toReview : changes.data;

  return (
    <>
      <PageTitle title="Changes" subtitle="Proposed, approved and applied changes to your Xero organisations. Start one from the Gaps page or an organisation's mapping." />
      <ErrorNote message={changes.error} />
      <div className="mb-3 max-w-sm">
        <Segmented<Filter> value={filter} onChange={setFilter}
          options={[{ value: "all", label: "All" }, { value: "review", label: `Needs review (${toReview.length})` }]} />
      </div>
      <Card className="divide-y divide-border">
        {shown.length === 0 && (
          <p className="p-6 text-sm text-muted">{filter === "review" ? "Nothing waiting for review." : "No changes yet."}</p>
        )}
        {shown.map((c) => {
          const total = Object.values(c.item_counts).reduce((a, b) => a + b, 0);
          return (
            <Link key={c.id} href={`/w/${ws}/changes/${c.id}`} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm hover:bg-surface-sunken">
              <ChangeBadge status={c.status} />
              {c.needs_review && <Badge tone="amber">self-approved · needs review</Badge>}
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
