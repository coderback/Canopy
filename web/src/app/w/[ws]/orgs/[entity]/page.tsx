"use client";

import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { api, type GroupAccount, type MappingRow } from "@/lib/api";
import { useRole } from "@/lib/session";
import { useData } from "@/lib/use-data";
import {
  Badge, Button, Card, Code, ConfidenceBadge, EmptyState, ErrorNote, Icon, Loading, Menu, Notice, PageTitle, ProgressRing,
  SearchInput, Segmented, SourceBadge, SyncBadge, Tabs,
} from "@/components/ui";
import { GroupPicker } from "@/components/group-picker";
import { TrackingMapping } from "./tracking-mapping";

type Filter = "review" | "confirmed" | "all";
type Section = "accounts" | "tracking";

// Needs a human: anything suggested, rejected, or not yet looked at.
const needsReview = (r: MappingRow) => !r.mapping || r.mapping.status !== "confirmed";

export default function OrgMapping() {
  const { ws, entity } = useParams<{ ws: string; entity: string }>();
  const { isAdmin, role } = useRole(ws);
  const router = useRouter();
  const rows = useData(() => api.mappings(ws, entity));
  const standard = useData(() => api.standard(ws));
  const entities = useData(() => api.entities(ws));
  const settings = useData(() => api.settings(ws));
  const [section, setSection] = useState<Section>("accounts");
  const [filter, setFilter] = useState<Filter>("review");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const all = useMemo(() => rows.data ?? [], [rows.data]);
  const counts = useMemo(() => {
    const review = all.filter(needsReview).length;
    return { review, confirmed: all.length - review, all: all.length };
  }, [all]);

  if (!rows.data || !standard.data || !entities.data || !settings.data) return <Loading />;
  const canPropose = settings.data.changes_enabled && ["owner", "admin", "preparer"].includes(role ?? "");
  const org = entities.data.find((e) => e.id === entity);
  const q = query.trim().toLowerCase();
  const shown = all.filter((r) => {
    if (filter !== "all" && (filter === "review" ? !needsReview(r) : needsReview(r))) return false;
    if (!q) return true;
    return `${r.account.code ?? ""} ${r.account.name} ${r.group_account?.name ?? ""} ${r.group_account?.code ?? ""}`.toLowerCase().includes(q);
  });
  const exactPending = all.filter((r) => r.mapping?.status === "suggested" && r.mapping.source === "exact").length;
  const unmatchedCount = all.filter((r) => r.mapping?.source === "unmatched" && r.mapping.status !== "confirmed").length;
  const active = standard.data.filter((g) => g.status === "active");
  const pct = all.length ? counts.confirmed / all.length : 0;

  // One-click changes start a draft for review; nothing is written until approved.
  async function propose(title: string, operation: "update_account" | "archive_account", accountId: string,
    payload?: Record<string, unknown>) {
    setError(null);
    try {
      const change = await api.createChange(ws, title, [
        { operation, entity_id: entity, entity_account_id: accountId, payload: payload ?? null },
      ]);
      router.push(`/w/${ws}/changes/${change.id}`);
    } catch (err) {
      setError((err as Error).message);
    }
  }

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
        title={org?.name ?? "Mapping"}
        badge={org && <SyncBadge status={org.sync_status} />}
        subtitle="Match each account in this organisation to the group standard. Suggestions are never final until you confirm them."
        action={isAdmin && section === "accounts" && (
          <>
            <Button variant="outline" icon="refresh" onClick={() => act(() => api.resuggest(ws, entity), "Re-suggesting in the background. Refresh in a moment.")}>
              Re-suggest
            </Button>
            <Button icon="check" disabled={exactPending === 0} onClick={() => act(() => api.confirmExact(ws, entity))}>
              Confirm {exactPending} exact {exactPending === 1 ? "match" : "matches"}
            </Button>
          </>
        )}
      />
      <ErrorNote message={error ?? rows.error} />
      {notice && <Notice tone="info" className="mb-4">{notice}</Notice>}

      <Card className="mb-6 grid items-center gap-5 p-5 sm:grid-cols-[auto_1fr_auto]">
        <ProgressRing value={pct} size={64} stroke={6} tone={pct >= 0.9 ? "brand" : pct >= 0.5 ? "amber" : "red"} />
        <div>
          <p className="text-[15px] font-semibold">
            <span className="tnum">{counts.confirmed}</span> of <span className="tnum">{all.length}</span> accounts confirmed
          </p>
          <p className="mt-0.5 text-[13px] text-muted">
            {counts.review === 0
              ? "Every active account is mapped. Nicely done."
              : <>{counts.review} still need a decision{unmatchedCount > 0 && <>, {unmatchedCount} with no match found</>}.</>}
          </p>
        </div>
        <dl className="hidden gap-6 text-right sm:flex">
          <Stat label="To review" value={counts.review} tone="amber" />
          <Stat label="Confirmed" value={counts.confirmed} tone="good" />
        </dl>
      </Card>

      <Tabs<Section> value={section} onChange={setSection}
        options={[{ value: "accounts", label: "Accounts", icon: "layers", count: all.length }, { value: "tracking", label: "Tracking categories", icon: "tag" }]} />

      <div className="mt-5">
        {section === "accounts" ? (
          <>
            {standard.data.length === 0 && (
              <Notice tone="warn" className="mb-4">Set up the group standard first. Suggestions appear once it exists.</Notice>
            )}
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <Segmented<Filter> value={filter} onChange={setFilter}
                options={[
                  { value: "review", label: "Needs review", count: counts.review },
                  { value: "confirmed", label: "Confirmed", count: counts.confirmed },
                  { value: "all", label: "All", count: counts.all },
                ]} />
              <SearchInput value={query} onChange={setQuery} label="Search accounts" placeholder="Search by code or name…" className="w-full sm:w-72" />
            </div>
            <Card className="overflow-hidden">
              <div className="hidden grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_232px] gap-4 border-b border-border bg-surface-sunken/60 px-5 py-2.5 md:grid">
                <span className="eyebrow">This organisation</span>
                <span className="eyebrow">Group standard</span>
                <span className="eyebrow text-right">Decision</span>
              </div>
              {shown.length === 0 ? (
                <EmptyState icon={filter === "review" ? "check" : "search"} title={q ? "No accounts match your search" : filter === "review" ? "All caught up" : "Nothing here"}>
                  {q ? "Try a different code or name." : filter === "review" ? "There are no accounts waiting for a decision." : undefined}
                </EmptyState>
              ) : (
                <ul className="divide-y divide-border">
                  {shown.map((r) => (
                    <Row key={r.account.id} row={r} groups={active} canEdit={isAdmin} canPropose={canPropose}
                      decide={(action, groupId) => act(() => api.decide(ws, r.mapping!.id, { action, group_account_id: groupId ?? null }))}
                      rename={(name) => propose(`Rename ${r.account.code ?? ""} ${r.account.name} in ${org?.name ?? "org"}`,
                        "update_account", r.account.id, { name })}
                      archive={() => propose(`Archive ${r.account.code ?? ""} ${r.account.name} in ${org?.name ?? "org"}`,
                        "archive_account", r.account.id)} />
                  ))}
                </ul>
              )}
            </Card>
          </>
        ) : (
          <TrackingMapping ws={ws} entity={entity} orgName={org?.name ?? "This organisation"} isAdmin={isAdmin} canPropose={canPropose} />
        )}
      </div>
    </>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: "amber" | "good" }) {
  return (
    <div>
      <dt className="eyebrow">{label}</dt>
      <dd className={`tnum mt-1 text-2xl font-semibold ${tone === "amber" && value > 0 ? "text-amber-700" : tone === "good" ? "text-brand-strong" : ""}`}>{value}</dd>
    </div>
  );
}

function Row({ row, groups, canEdit, canPropose, decide, rename, archive }: {
  row: MappingRow;
  groups: GroupAccount[];
  canEdit: boolean;
  canPropose: boolean;
  decide: (action: "confirm" | "reject" | "assign", groupId?: string | null) => void;
  rename: (name: string) => void;
  archive: () => void;
}) {
  const [assigning, setAssigning] = useState(false);
  const m = row.mapping;
  const unmatched = m?.source === "unmatched" && m.status !== "confirmed";
  const confirmed = m?.status === "confirmed";

  const menu = canPropose ? [
    ...(confirmed && row.group_account && row.group_account.name !== row.account.name
      ? [{ label: `Propose renaming to “${row.group_account.name}”`, icon: "edit" as const, onClick: () => rename(row.group_account!.name) }]
      : []),
    { label: "Propose archiving this account", icon: "archive" as const, onClick: archive, danger: true },
  ] : [];

  return (
    <li className="grid gap-x-4 gap-y-3 px-5 py-4 transition hover:bg-surface-hover/60 md:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_232px] md:items-start">
      {/* Local account */}
      <div className="min-w-0">
        <p className="flex items-center gap-2 font-medium">
          <Code>{row.account.code ?? "—"}</Code>
          <span className="truncate">{row.account.name}</span>
        </p>
        <p className="mt-1 text-xs capitalize text-subtle">{row.account.type.toLowerCase()}</p>
      </div>

      {/* Suggested / confirmed group account */}
      <div className="min-w-0 space-y-1.5">
        {!m ? (
          <p className="text-sm text-muted">No suggestion yet.</p>
        ) : (
          <>
            <p className="flex items-center gap-2 text-sm">
              <Icon name="arrowRight" size={15} className={unmatched ? "text-amber-500" : "text-brand"} />
              {row.group_account ? (
                <>
                  <Code>{row.group_account.code}</Code>
                  <b className="truncate font-medium">{row.group_account.name}</b>
                </>
              ) : (
                <span className={unmatched ? "font-medium text-amber-700" : "text-muted"}>
                  {unmatched ? "Needs a group account" : "Local only (no group equivalent)"}
                </span>
              )}
            </p>
            <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 pl-[23px]">
              <SourceBadge source={m.source} />
              {m.status === "suggested" && m.source !== "unmatched" && <ConfidenceBadge value={m.confidence} />}
              {confirmed && <Badge tone="emerald" dot>Confirmed</Badge>}
              {m.status === "rejected" && <Badge tone="red" dot>Rejected</Badge>}
            </div>
            {m.reasoning && <p className="line-clamp-2 pl-[23px] text-xs leading-relaxed text-muted" title={m.reasoning}>{m.reasoning}</p>}
          </>
        )}
      </div>

      {/* Decision */}
      <div className="flex items-center gap-1.5 md:justify-end">
        {canEdit && m && (
          <>
            {/* Nothing to confirm on an unmatched row: a person has to choose. */}
            {!confirmed && !unmatched && <Button size="sm" icon="check" onClick={() => decide("confirm")}>Confirm</Button>}
            {m.status === "suggested" && !unmatched && <Button size="sm" variant="ghost" onClick={() => decide("reject")}>Reject</Button>}
            <Button size="sm" variant={unmatched ? "primary" : "outline"} onClick={() => setAssigning(true)}>
              {unmatched ? "Choose…" : "Change"}
            </Button>
          </>
        )}
        <Menu items={menu} />
      </div>

      {assigning && (
        <GroupPicker open onClose={() => setAssigning(false)} title="Choose a group account"
          subject={<>Mapping <b className="text-foreground">{row.account.code ?? "—"} {row.account.name}</b></>}
          choices={groups.map((g) => ({ id: g.id, name: g.name, code: g.code, meta: g.type.toLowerCase() }))}
          current={confirmed ? (row.group_account?.id ?? null) : undefined}
          onSave={(id) => decide("assign", id)} />
      )}
    </li>
  );
}
