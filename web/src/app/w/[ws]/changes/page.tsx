"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api } from "@/lib/api";
import { useData } from "@/lib/use-data";
import { Avatar, Badge, Card, ChangeBadge, EmptyState, ErrorNote, Icon, Loading, PageTitle, Segmented } from "@/components/ui";

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
      <PageTitle title="Changes"
        subtitle="Proposed, approved and applied changes to your Xero organisations. Start one from the Gaps page or an organisation's mapping." />
      <ErrorNote message={changes.error} />
      <div className="mb-4">
        <Segmented<Filter> value={filter} onChange={setFilter}
          options={[{ value: "all", label: "All", count: changes.data.length }, { value: "review", label: "Needs review", count: toReview.length }]} />
      </div>
      <Card className="overflow-hidden">
        {shown.length === 0 ? (
          <EmptyState icon={filter === "review" ? "check" : "changes"}
            title={filter === "review" ? "Nothing waiting for review" : "No changes yet"}>
            {filter === "review"
              ? "Self-approved changes show up here until someone else has looked at them."
              : "Select gaps on the Gaps page, or propose a rename from an organisation's mapping, to start a change."}
          </EmptyState>
        ) : (
          <ul className="divide-y divide-border">
            {shown.map((c) => {
              const total = Object.values(c.item_counts).reduce((a, b) => a + b, 0);
              const author = c.author.name || c.author.email;
              return (
                <li key={c.id}>
                  <Link href={`/w/${ws}/changes/${c.id}`}
                    className="group flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-4 transition hover:bg-surface-hover">
                    <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-surface-sunken text-muted ring-1 ring-inset ring-border">
                      <Icon name="changes" size={18} />
                    </span>
                    <div className="min-w-0 flex-1 basis-60">
                      <p className="truncate font-medium">{c.title}</p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
                        <Avatar name={author} size={16} /> {author}
                        <span aria-hidden>·</span> {new Date(c.created_at).toLocaleDateString()}
                        <span aria-hidden>·</span> <span className="tnum">{total}</span> {total === 1 ? "item" : "items"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      {c.needs_review && <Badge tone="amber" dot>Needs review</Badge>}
                      <ChangeBadge status={c.status} />
                    </div>
                    <Icon name="chevronRight" size={17} className="text-subtle transition group-hover:translate-x-0.5 group-hover:text-foreground" />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </>
  );
}
