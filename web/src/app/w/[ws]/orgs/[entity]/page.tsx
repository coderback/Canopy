"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { api, type GroupAccount, type MappingRow } from "@/lib/api";
import { useRole } from "@/lib/session";
import { useData } from "@/lib/use-data";
import { Badge, Button, Card, ConfidenceBadge, ErrorNote, Loading, PageTitle, Segmented, SourceBadge } from "@/components/ui";

type Filter = "review" | "confirmed" | "all";

// Needs a human: anything suggested, rejected, or not yet looked at.
const needsReview = (r: MappingRow) => !r.mapping || r.mapping.status !== "confirmed";

export default function OrgMapping() {
  const { ws, entity } = useParams<{ ws: string; entity: string }>();
  const { isAdmin } = useRole(ws);
  const rows = useData(() => api.mappings(ws, entity));
  const standard = useData(() => api.standard(ws));
  const entities = useData(() => api.entities(ws));
  const [filter, setFilter] = useState<Filter>("review");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  if (!rows.data || !standard.data || !entities.data) return <Loading />;
  const org = entities.data.find((e) => e.id === entity);
  const all = rows.data;
  const shown = all.filter((r) => filter === "all" || (filter === "review" ? needsReview(r) : !needsReview(r)));
  const exactPending = all.filter((r) => r.mapping?.status === "suggested" && r.mapping.source === "exact").length;
  const active = standard.data.filter((g) => g.status === "active");

  async function act(fn: () => Promise<unknown>, message?: string) {
    setError(null);
    try {
      await fn();
      await rows.reload();
      if (message) setNotice(message);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <PageTitle
        title={org ? `${org.name}: mapping` : "Mapping"}
        subtitle={`${all.length - all.filter(needsReview).length} of ${all.length} active accounts confirmed.`}
        action={isAdmin && (
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => act(() => api.resuggest(ws, entity), "Re-suggesting in the background; refresh in a moment.")}>Re-suggest</Button>
            <Button disabled={exactPending === 0} onClick={() => act(() => api.confirmExact(ws, entity))}>
              Confirm {exactPending} exact {exactPending === 1 ? "match" : "matches"}
            </Button>
          </div>
        )}
      />
      <ErrorNote message={error ?? rows.error} />
      {notice && <p className="mb-3 text-sm text-muted">{notice}</p>}
      {standard.data.length === 0 && <Card className="mb-4 p-4 text-sm text-muted">Set up the group standard first; suggestions appear once it exists.</Card>}
      <div className="mb-3 max-w-sm">
        <Segmented<Filter> value={filter} onChange={setFilter}
          options={[{ value: "review", label: "Needs review" }, { value: "confirmed", label: "Confirmed" }, { value: "all", label: "All" }]} />
      </div>
      <Card className="divide-y divide-border">
        {shown.length === 0 && <p className="p-6 text-sm text-muted">Nothing here.</p>}
        {shown.map((r) => (
          <Row key={r.account.id} row={r} groups={active} canEdit={isAdmin}
            decide={(action, groupId) => act(() => api.decide(ws, r.mapping!.id, { action, group_account_id: groupId ?? null }))} />
        ))}
      </Card>
    </>
  );
}

function Row({ row, groups, canEdit, decide }: {
  row: MappingRow;
  groups: GroupAccount[];
  canEdit: boolean;
  decide: (action: "confirm" | "reject" | "assign", groupId?: string | null) => void;
}) {
  const [assigning, setAssigning] = useState(false);
  const [choice, setChoice] = useState("");
  const m = row.mapping;
  const unmatched = m?.source === "unmatched" && m.status !== "confirmed";
  const target = row.group_account
    ? `${row.group_account.code} ${row.group_account.name}`
    : unmatched ? "Needs a group account" : "No group equivalent";

  return (
    <div className="grid gap-3 px-4 py-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto] md:items-start">
      <div>
        <p className="font-medium text-slate-900"><span className="font-mono text-muted">{row.account.code ?? "—"}</span> {row.account.name}</p>
        <p className="text-xs text-muted">{row.account.type}</p>
      </div>
      <div className="space-y-1">
        {!m ? (
          <p className="text-sm text-muted">No suggestion yet.</p>
        ) : (
          <>
            <p className="text-sm"><span className="text-muted">→</span> <b>{target}</b></p>
            <div className="flex flex-wrap gap-1.5">
              <SourceBadge source={m.source} />
              {m.status === "suggested" && m.source !== "unmatched" && <ConfidenceBadge value={m.confidence} />}
              {m.status === "confirmed" && <Badge tone="emerald">confirmed</Badge>}
              {m.status === "rejected" && <Badge tone="red">rejected</Badge>}
            </div>
            <p className="text-xs text-slate-600">{m.reasoning}</p>
          </>
        )}
      </div>
      {canEdit && m && (
        <div className="flex flex-wrap items-center justify-end gap-1">
          {assigning ? (
            <>
              <select value={choice} onChange={(e) => setChoice(e.target.value)} aria-label={`Group account for ${row.account.name}`}
                className="max-w-56 rounded-lg border border-border-strong px-2 py-1.5 text-sm">
                <option value="">Choose…</option>
                <option value="local">Local only (no group equivalent)</option>
                {groups.map((g) => <option key={g.id} value={g.id}>{g.code} {g.name}</option>)}
              </select>
              <Button disabled={!choice} onClick={() => { decide("assign", choice === "local" ? null : choice); setAssigning(false); }}>Save</Button>
              <Button variant="ghost" onClick={() => setAssigning(false)}>Cancel</Button>
            </>
          ) : (
            <>
              {/* Nothing to confirm on an unmatched row: a person has to choose. */}
              {m.status !== "confirmed" && !unmatched && <Button onClick={() => decide("confirm")}>Confirm</Button>}
              {m.status === "suggested" && !unmatched && <Button variant="ghost" onClick={() => decide("reject")}>Reject</Button>}
              <Button variant={unmatched ? "primary" : "ghost"} onClick={() => setAssigning(true)}>{unmatched ? "Choose…" : "Change…"}</Button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
