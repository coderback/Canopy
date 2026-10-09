"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import { api, connectUrl, type Entity, type GapMatrix, type GroupAccount } from "@/lib/api";
import { useRole, useSession } from "@/lib/session";
import { useData } from "@/lib/use-data";
import {
  Badge, Button, ButtonLink, Card, EmptyState, ErrorNote, Icon, Loading, Menu, Notice, PageTitle, Panel, ProgressRing, StatCard,
  SyncBadge,
} from "@/components/ui";

const BUSY = new Set(["queued", "running"]);

type Coverage = { mapped: number; pending: number; gap: number; total: number };

/** Per-organisation coverage of the group standard, derived from the gap matrix. */
function coverageByOrg(gaps: GapMatrix | null): Map<string, Coverage> {
  const out = new Map<string, Coverage>();
  if (!gaps) return out;
  for (const e of gaps.entities) out.set(e.id, { mapped: 0, pending: 0, gap: 0, total: 0 });
  for (const r of gaps.rows) {
    for (const e of gaps.entities) {
      const c = r.cells[e.id];
      const cov = out.get(e.id);
      if (!c || !cov) continue;
      cov.total += 1;
      if (c.state === "mapped") cov.mapped += 1;
      else if (c.state === "pending") cov.pending += 1;
      else if (c.state === "gap") cov.gap += 1;
    }
  }
  return out;
}

export default function Overview() {
  const { ws } = useParams<{ ws: string }>();
  const { me } = useSession();
  const { isAdmin } = useRole(ws);
  const entities = useData(() => api.entities(ws), (list: Entity[]) => list.some((e) => BUSY.has(e.sync_status)));
  const standard = useData(() => api.standard(ws));
  const toReview = useData(() => api.changes(ws, true));
  const changes = useData(() => api.changes(ws));
  const gaps = useData(() => api.gaps(ws));

  const coverage = useMemo(() => coverageByOrg(gaps.data), [gaps.data]);

  if (!entities.data || !standard.data) return <Loading />;
  const orgs = entities.data;
  const std = standard.data;
  const activeStd = std.filter((g) => g.status === "active");

  async function sync(e: Entity) {
    try {
      await api.syncEntity(ws, e.id);
      await entities.reload();
    } catch (err) {
      entities.setError((err as Error).message);
    }
  }

  async function act(fn: () => Promise<unknown>) {
    try {
      await fn();
      await Promise.all([entities.reload(), gaps.reload()]);
    } catch (err) {
      entities.setError((err as Error).message);
    }
  }

  const needsReconnect = orgs.filter((o) => o.status === "needs_reconnect");
  const connected = orgs.filter((o) => o.status !== "disconnected");
  // Disconnected organisations are listed last.
  const listed = [...connected, ...orgs.filter((o) => o.status === "disconnected")];

  const cov = [...coverage.values()];
  const totalCells = cov.reduce((n, c) => n + c.total, 0);
  const mappedCells = cov.reduce((n, c) => n + c.mapped, 0);
  const gapCells = cov.reduce((n, c) => n + c.gap, 0);
  const pendingCells = cov.reduce((n, c) => n + c.pending, 0);
  const coveragePct = totalCells ? Math.round((mappedCells / totalCells) * 100) : 0;
  const openChanges = (changes.data ?? []).filter((c) => ["draft", "submitted", "approved", "executing"].includes(c.status)).length;
  const reviewCount = toReview.data?.length ?? 0;
  const firstName = (me?.user.name || me?.user.email || "").split(/[\s@]/)[0];
  const ready = orgs.length > 0 && activeStd.length > 0;

  return (
    <>
      <PageTitle
        title={`Welcome back${firstName ? `, ${firstName}` : ""}`}
        subtitle={ready
          ? "Here's how closely your organisations line up with the group standard."
          : "Let's get your group connected and mapped. It only takes a few steps."}
        action={isAdmin && (
          <ButtonLink href={connectUrl(ws)} external variant="dark" icon="link">Connect Xero organisations</ButtonLink>
        )}
      />
      <ErrorNote message={entities.error ?? standard.error} />

      {reviewCount > 0 && (
        <Notice tone="warn" className="mb-5"
          action={<Link href={`/w/${ws}/changes?review=1`} className="inline-flex items-center gap-1 text-sm font-medium underline-offset-2 hover:underline">Open review queue <Icon name="arrowRight" size={14} /></Link>}>
          <b>{reviewCount}</b> self-approved {reviewCount === 1 ? "change is" : "changes are"} waiting for someone else to review {reviewCount === 1 ? "it" : "them"}.
        </Notice>
      )}

      {needsReconnect.length > 0 && (
        <Notice tone="warn" className="mb-5"
          action={isAdmin ? <ButtonLink href={connectUrl(ws)} external size="sm" variant="dark" icon="link">Reconnect in Xero</ButtonLink> : undefined}>
          <b>{needsReconnect.map((o) => o.name).join(", ")}</b> {needsReconnect.length === 1 ? "needs" : "need"} reconnecting.
          Canopy can&apos;t reach {needsReconnect.length === 1 ? "it" : "them"}, so the data may be out of date, and changes are
          paused until {needsReconnect.length === 1 ? "it's" : "they're"} reconnected.
        </Notice>
      )}

      {!ready || orgs.every((o) => o.sync_status !== "ok") ? (
        <Setup orgs={orgs} standard={std} ws={ws} isAdmin={isAdmin} />
      ) : null}

      <div className="mb-6 grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard featured className="col-span-2 xl:col-span-1" label="Group coverage" value={coveragePct} unit="%" icon="layers"
          hint={totalCells ? `${mappedCells} of ${totalCells} account slots mapped` : "Set up the group standard to begin"} />
        <StatCard label="Organisations" value={orgs.length} icon="building"
          hint={orgs.length ? `${orgs.filter((o) => o.sync_status === "ok").length} synced` : "None connected yet"} />
        <StatCard label="Open gaps" value={gapCells} icon="gap" href={`/w/${ws}/gaps`}
          tone={gapCells ? "warn" : "good"}
          hint={gapCells ? `${pendingCells} more awaiting review` : totalCells ? "Everything is covered" : "—"} />
        <StatCard label="Open changes" value={openChanges} icon="changes" href={`/w/${ws}/changes`}
          tone={reviewCount ? "warn" : "neutral"}
          hint={reviewCount ? `${reviewCount} need a second reviewer` : "Nothing waiting"} />
      </div>

      <Panel title="Organisations"
        hint={`${connected.length} connected${orgs.length > connected.length ? ` · ${orgs.length - connected.length} disconnected` : ""}`}
        action={isAdmin && <Button variant="outline" size="sm" icon="plus" onClick={() => { window.location.href = connectUrl(ws); }}>Connect</Button>}>
        {orgs.length === 0 ? (
          <EmptyState icon="building" title="No organisations connected yet"
            action={isAdmin ? <ButtonLink href={connectUrl(ws)} external icon="link">Connect Xero organisations</ButtonLink> : undefined}>
            Connecting is read-only: Canopy can see charts of accounts but can&apos;t change anything in Xero.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-border">
            {listed.map((e) => (
              <OrgRow key={e.id} org={e} ws={ws} cov={coverage.get(e.id)} isAdmin={isAdmin} onSync={() => sync(e)}
                onDisconnect={(removeNow) => act(() => api.disconnectEntity(ws, e.id, removeNow))}
                onRemoveData={() => act(() => api.removeEntityData(ws, e.id))} />
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}

function OrgRow({ org: e, ws, cov, isAdmin, onSync, onDisconnect, onRemoveData }: {
  org: Entity; ws: string; cov?: Coverage; isAdmin: boolean; onSync: () => void;
  onDisconnect: (removeNow: boolean) => Promise<void>; onRemoveData: () => Promise<void>;
}) {
  // Disconnecting is confirmed inline (no browser dialog): what happens to the data is the choice.
  const [confirming, setConfirming] = useState(false);
  const [working, setWorking] = useState(false);
  const busy = BUSY.has(e.sync_status);
  const disconnected = e.status === "disconnected";
  const run = async (fn: () => Promise<void>) => { setWorking(true); await fn(); setWorking(false); setConfirming(false); };
  const menu = !isAdmin ? [] : disconnected
    ? (e.purged_at ? [] : [{ label: "Remove its data now", icon: "trash" as const, danger: true, onClick: () => run(onRemoveData) }])
    : [{ label: "Disconnect…", icon: "x" as const, danger: true, onClick: () => setConfirming(true) }];
  const pct = cov && cov.total ? cov.mapped / cov.total : 0;
  const tone = pct >= 0.9 ? "brand" : pct >= 0.5 ? "amber" : "red";
  return (
    <li className={`group flex flex-wrap items-center gap-x-5 gap-y-3 px-4 py-3.5 transition hover:bg-surface-hover sm:px-5 ${disconnected ? "opacity-70" : ""}`}>
      <Link href={`/w/${ws}/orgs/${e.id}`} className="flex min-w-0 flex-1 basis-64 items-center gap-4">
        <ProgressRing value={pct} tone={cov?.total ? tone : "brand"} label={cov?.total ? undefined : "—"} />
        <span className="min-w-0">
          <span className="block truncate font-medium">{e.name}</span>
          <span className="mt-0.5 block text-xs text-muted">
            {cov?.total
              ? <>
                  <span className="tnum">{cov.mapped}</span> mapped
                  {cov.pending > 0 && <> · <span className="tnum text-amber-700">{cov.pending}</span> to review</>}
                  {cov.gap > 0 && <> · <span className="tnum text-red-700">{cov.gap}</span> {cov.gap === 1 ? "gap" : "gaps"}</>}
                </>
              : "Not mapped yet"}
          </span>
        </span>
      </Link>

      <div className="flex min-w-36 flex-col items-start gap-1">
        {e.status === "active" ? <SyncBadge status={e.sync_status} />
          : e.status === "needs_reconnect" ? <Badge tone="amber" dot>Needs reconnecting</Badge>
          : <Badge tone="slate" dot>Disconnected</Badge>}
        <span className="text-xs text-subtle">
          {disconnected
            ? (e.purged_at ? "Data removed" : e.purge_after ? `Data removed ${new Date(e.purge_after).toLocaleDateString()}` : "")
            : e.last_synced_at ? `Synced ${relative(e.last_synced_at)}` : "Never synced"}
        </span>
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        {isAdmin && e.status === "active" && (
          <Button variant="ghost" size="sm" icon="refresh" onClick={onSync} disabled={busy}>
            {busy ? "Syncing" : "Sync"}
          </Button>
        )}
        {isAdmin && e.status !== "active" && (
          <ButtonLink href={connectUrl(ws)} external size="sm" variant="outline" icon="link">Reconnect</ButtonLink>
        )}
        {!disconnected && (
          <Link href={`/w/${ws}/orgs/${e.id}`}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border-strong bg-surface px-3 text-[13px] font-medium shadow-sm transition hover:bg-surface-hover">
            Review mapping <Icon name="arrowRight" size={14} />
          </Link>
        )}
        <Menu items={menu} label={`More actions for ${e.name}`} />
      </div>
      {e.status === "needs_reconnect" && e.status_reason && (
        <p className="basis-full rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{e.status_reason}</p>
      )}
      {confirming && (
        <div className="basis-full rounded-xl border border-red-200 bg-red-50/60 p-3.5 text-sm">
          <p className="font-medium">Disconnect {e.name}?</p>
          <p className="mt-1 text-[13px] leading-relaxed text-muted">
            Xero drops Canopy&apos;s connection to it straight away. Its accounts, mappings and tracking stay in Canopy for
            30 days, so reconnecting restores them, and are then removed. The audit log and change history are kept.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="danger" disabled={working} onClick={() => run(() => onDisconnect(false))}>Disconnect</Button>
            <Button size="sm" variant="outline" disabled={working} onClick={() => run(() => onDisconnect(true))}>Disconnect and remove its data now</Button>
            <Button size="sm" variant="ghost" disabled={working} onClick={() => setConfirming(false)}>Cancel</Button>
          </div>
        </div>
      )}
      {e.status === "active" && e.sync_error && (
        <p className="basis-full rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">{e.sync_error}</p>
      )}
    </li>
  );
}

function Setup({ orgs, standard, ws, isAdmin }: { orgs: Entity[]; standard: GroupAccount[]; ws: string; isAdmin: boolean }) {
  const steps = [
    { done: orgs.length > 0, title: "Connect your Xero organisations", body: "Read-only. Canopy mirrors each chart of accounts.", cta: isAdmin ? { label: "Connect", href: connectUrl(ws), external: true } : undefined },
    { done: orgs.some((e) => e.sync_status === "ok"), title: "Wait for the first sync", body: "Usually under a minute per organisation.", cta: undefined },
    { done: standard.length > 0, title: "Set up the group standard", body: "Start from one org's chart or import a CSV.", cta: { label: "Set up", href: `/w/${ws}/standard`, external: false } },
    { done: false, title: "Review each org's mapping", body: "Confirm, reject or reassign the suggestions, then check the gaps.", cta: orgs.length ? { label: "Open gaps", href: `/w/${ws}/gaps`, external: false } : undefined },
  ];
  const done = steps.filter((s) => s.done).length;
  const current = steps.findIndex((s) => !s.done);
  return (
    <Card className="mb-6 overflow-hidden">
      <div className="flex items-center justify-between gap-4 border-b border-border bg-brand-soft/60 px-5 py-3.5">
        <div>
          <p className="text-sm font-semibold text-brand-deep">Getting started</p>
          <p className="text-xs text-brand-strong/80">{done} of {steps.length} steps done</p>
        </div>
        <ProgressRing value={done / steps.length} size={40} stroke={4} label={`${done}/${steps.length}`} />
      </div>
      <ol className="grid divide-y divide-border sm:grid-cols-2 sm:divide-y-0 xl:grid-cols-4 xl:divide-x">
        {steps.map((s, i) => (
          <li key={s.title} className={`flex flex-col gap-3 p-5 ${i === current ? "bg-surface" : ""}`}>
            <span className={`grid h-7 w-7 place-items-center rounded-full text-[13px] font-semibold ${
              s.done ? "bg-brand text-white" : i === current ? "bg-ink text-white" : "bg-surface-sunken text-subtle ring-1 ring-inset ring-border"}`}>
              {s.done ? <Icon name="check" size={15} /> : i + 1}
            </span>
            <div className="flex-1">
              <p className={`text-sm font-medium ${s.done ? "text-muted line-through decoration-border-strong" : ""}`}>{s.title}</p>
              <p className="mt-1 text-[13px] leading-relaxed text-muted">{s.body}</p>
            </div>
            {i === current && s.cta && (
              <div>
                <ButtonLink href={s.cta.href} external={s.cta.external} size="sm" variant="dark">{s.cta.label}</ButtonLink>
              </div>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}

function relative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return days < 30 ? `${days}d ago` : new Date(iso).toLocaleDateString();
}
