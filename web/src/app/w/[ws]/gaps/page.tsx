"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { api, exportUrl } from "@/lib/api";
import { useRole } from "@/lib/session";
import { useData } from "@/lib/use-data";
import {
  ActionBar, Button, ButtonLink, Card, Code, EmptyState, ErrorNote, GAP_CELL as CELL, Icon, Loading, PageTitle, ProgressBar,
  Segmented, StatCard, Tabs,
} from "@/components/ui";
import { TrackingGaps } from "./tracking-gaps";

type Section = "accounts" | "tracking";

function GapLegend() {
  const items = [
    { key: "mapped", text: "Mapped" },
    { key: "pending", text: "Suggested, awaiting review" },
    { key: "gap", text: "Gap" },
  ] as const;
  return (
    <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted" aria-label="Legend">
      {items.map((i) => (
        <li key={i.key} className="flex items-center gap-1.5">
          <span className={`inline-block h-3.5 w-3.5 rounded ${CELL[i.key].cls}`} /> {i.text}
        </li>
      ))}
    </ul>
  );
}

export default function GapsPage() {
  const { ws } = useParams<{ ws: string }>();
  const router = useRouter();
  const { role } = useRole(ws);
  const gaps = useData(() => api.gaps(ws));
  const settings = useData(() => api.settings(ws));
  const [section, setSection] = useState<Section>("accounts");
  const [only, setOnly] = useState<"gaps" | "all">("gaps");
  // Selected gaps to fix, as "groupAccountId:entityId".
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!gaps.data || !settings.data) return <Loading />;
  const canPropose = settings.data.changes_enabled && ["owner", "admin", "preparer"].includes(role ?? "");

  function toggle(key: string) {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function propose() {
    setError(null);
    setBusy(true);
    try {
      const items = [...picked].map((key) => {
        const [groupId, entityId] = key.split(":");
        return { operation: "create_account" as const, entity_id: entityId, group_account_id: groupId };
      });
      const change = await api.createChange(ws, `Fill ${items.length} gap${items.length === 1 ? "" : "s"}`, items,
        "Create group accounts missing from these organisations.");
      router.push(`/w/${ws}/changes/${change.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  const { entities, rows } = gaps.data;
  const shown = only === "gaps" ? rows.filter((r) => r.gaps > 0) : rows;
  const totalGaps = rows.reduce((n, r) => n + r.gaps, 0);
  const cells = rows.flatMap((r) => entities.map((e) => r.cells[e.id]?.state));
  const mapped = cells.filter((s) => s === "mapped").length;
  const pending = cells.filter((s) => s === "pending").length;
  const coverage = cells.length ? mapped / cells.length : 0;

  // Per-organisation coverage, shown in the matrix header.
  const orgCoverage = new Map(entities.map((e) => {
    const states = rows.map((r) => r.cells[e.id]?.state);
    return [e.id, states.length ? states.filter((s) => s === "mapped").length / states.length : 0];
  }));

  return (
    <>
      <PageTitle
        title="Gaps"
        subtitle="Group accounts and tracking with no confirmed mapping in an organisation. Select a gap to propose creating it."
        action={<ButtonLink href={exportUrl(ws)} external variant="outline" icon="download">Export mapping (CSV)</ButtonLink>}
      />
      <ErrorNote message={error ?? gaps.error} />

      <div className="mb-6 grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard featured className="col-span-2 xl:col-span-1" label="Coverage" value={Math.round(coverage * 100)} unit="%" icon="layers"
          hint={`${mapped} of ${cells.length} slots mapped`} />
        <StatCard label="Gaps" value={totalGaps} icon="gap" tone={totalGaps ? "warn" : "good"}
          hint={totalGaps ? "Missing from at least one org" : "No gaps, nicely done"} />
        <StatCard label="Awaiting review" value={pending} icon="clock" tone={pending ? "warn" : "neutral"}
          hint={pending ? "Suggested, not confirmed" : "Nothing pending"} />
        <StatCard label="Organisations" value={entities.length} icon="building" hint={`${rows.length} group accounts`} />
      </div>

      <Tabs<Section> value={section} onChange={setSection}
        options={[{ value: "accounts", label: "Accounts", icon: "layers", count: totalGaps }, { value: "tracking", label: "Tracking categories", icon: "tag" }]} />

      <div className="mt-5 mb-3 flex flex-wrap items-center justify-between gap-3">
        <Segmented value={only} onChange={setOnly} options={[{ value: "gaps", label: "Only gaps" }, { value: "all", label: "Everything" }]} />
        <GapLegend />
      </div>

      {section === "accounts" ? (
        <>
          {canPropose && totalGaps > 0 && picked.size === 0 && (
            <p className="mb-3 flex items-center gap-2 text-[13px] text-muted">
              <Icon name="info" size={15} /> Click the red <span className="inline-block h-4 w-4 rounded bg-red-100 text-center text-[10px] leading-4 text-red-700 ring-1 ring-inset ring-red-200">✕</span> cells to select the accounts you want created in Xero.
            </p>
          )}
          <Card className="canopy-scroll overflow-x-auto">
            {rows.length === 0 ? (
              <EmptyState icon="layers" title="No group standard yet"
                action={<ButtonLink href={`/w/${ws}/standard`} icon="arrowRight">Set up the group standard</ButtonLink>}>
                Gaps appear once there&apos;s a standard to compare each organisation against.
              </EmptyState>
            ) : shown.length === 0 ? (
              <EmptyState icon="check" title="No gaps">Every group account is covered in every organisation.</EmptyState>
            ) : (
              <table className="w-full border-separate border-spacing-0 text-sm">
                <thead>
                  <tr>
                    <th className="sticky left-0 z-10 min-w-64 border-b border-border bg-surface-sunken px-5 py-3 text-left">
                      <span className="eyebrow">Group account</span>
                    </th>
                    {entities.map((e) => (
                      <th key={e.id} className="min-w-32 border-b border-border bg-surface-sunken px-3 py-3 text-left align-bottom">
                        <Link href={`/w/${ws}/orgs/${e.id}`} title={e.name} className="block max-w-36 truncate text-[13px] font-medium hover:text-brand-strong">{e.name}</Link>
                        <ProgressBar value={orgCoverage.get(e.id) ?? 0} className="mt-1.5" />
                        <span className="tnum mt-1 block text-[11px] font-normal text-muted">{Math.round((orgCoverage.get(e.id) ?? 0) * 100)}% covered</span>
                        {e.status === "needs_reconnect" && (
                          <span title="Needs reconnecting: this organisation's data may be out of date"
                            className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-amber-700">
                            <Icon name="alert" size={12} /> Needs reconnecting
                          </span>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r) => (
                    <tr key={r.group_account.id} className="group">
                      <td className="sticky left-0 z-10 border-b border-border bg-surface px-5 py-2.5 whitespace-nowrap group-hover:bg-surface-hover">
                        <span className="flex items-center gap-2.5"><Code>{r.group_account.code}</Code><span>{r.group_account.name}</span></span>
                      </td>
                      {entities.map((e) => {
                        const c = r.cells[e.id];
                        const style = CELL[c.state];
                        const key = `${r.group_account.id}:${e.id}`;
                        // No proposals for an org that needs reconnecting: they'd be blocked anyway.
                        const selectable = canPropose && c.state === "gap" && e.status === "active";
                        const on = picked.has(key);
                        return (
                          <td key={e.id} className="border-b border-border px-3 py-2.5 group-hover:bg-surface-hover">
                            {selectable ? (
                              <button type="button" onClick={() => toggle(key)} aria-pressed={on}
                                title={on ? "Selected: will be proposed" : "Gap: select to create"}
                                aria-label={`Create ${r.group_account.code} ${r.group_account.name} in ${e.name}`}
                                className={`grid h-7 w-7 place-items-center rounded-lg text-xs font-semibold transition ${on ? "bg-ink text-white ring-2 ring-brand ring-offset-1" : `${style.cls} hover:ring-2 hover:ring-red-300`}`}>
                                {on ? <Icon name="check" size={14} /> : style.label}
                              </button>
                            ) : (
                              <span title={style.name} className={`grid h-7 w-7 place-items-center rounded-lg text-xs font-semibold ${style.cls}`}>{style.label}</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
          <ActionBar show={picked.size > 0}>
            <span><b className="tnum">{picked.size}</b> {picked.size === 1 ? "account" : "accounts"} selected</span>
            <button onClick={() => setPicked(new Set())} className="text-white/60 underline-offset-2 hover:text-white hover:underline">Clear</button>
            <Button variant="primary" size="sm" disabled={busy} onClick={propose}>
              Propose creating {picked.size === 1 ? "it" : "them"}
            </Button>
          </ActionBar>
        </>
      ) : (
        <TrackingGaps ws={ws} only={only} canPropose={canPropose} />
      )}
    </>
  );
}
