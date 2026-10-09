"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { api, connectUrl } from "@/lib/api";
import { useRole } from "@/lib/session";
import { useData } from "@/lib/use-data";
import { Badge, ButtonLink, Card, ErrorNote, Icon, Loading, Notice, PageTitle, Panel, Switch } from "@/components/ui";

export default function SettingsPage() {
  const { ws } = useParams<{ ws: string }>();
  const { role, isAdmin } = useRole(ws);
  const settings = useData(() => api.settings(ws));
  const entities = useData(() => api.entities(ws));
  const [error, setError] = useState<string | null>(null);
  const isOwner = role === "owner";

  if (!settings.data || !entities.data) return <Loading />;
  const s = settings.data;

  async function toggle(field: "changes_enabled" | "allow_self_approval", value: boolean) {
    setError(null);
    try {
      await api.updateSettings(ws, { [field]: value });
      await settings.reload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <>
      <PageTitle title="Settings" subtitle="How this workspace is allowed to change your Xero organisations." />
      <ErrorNote message={error ?? settings.error} />
      {!s.writes_enabled_on_server && (
        <Notice tone="warn" className="mb-5">
          Writes to Xero are switched off on this server. Changes can be proposed and approved, but nothing will be written until an operator turns writes back on.
        </Notice>
      )}

      <div className="max-w-3xl space-y-6">
        <Panel title="Changes to Xero" hint={isOwner ? undefined : "Only the owner can change these"}>
          <ul className="divide-y divide-border">
            <Toggle
              icon="changes"
              label="Allow changes to Xero"
              help="Lets preparers propose, and approvers approve, changes to accounts in connected organisations. Each organisation also needs write access (below)."
              checked={s.changes_enabled} disabled={!isOwner} onChange={(v) => toggle("changes_enabled", v)}
            />
            <Toggle
              icon="shield"
              label="Allow self-approval when you're the only approver"
              help="Normally the person who proposes a change can't approve it. With this on, a lone approver can approve their own change, but only one that brings an organisation into line with the group standard (adding a group account, or renaming an account to its group name), never an archive or a code change, and only with a note saying why. Each one waits in a review queue until someone else looks at it."
              checked={s.allow_self_approval} disabled={!isOwner || !s.changes_enabled}
              onChange={(v) => toggle("allow_self_approval", v)}
              note={s.allow_self_approval && (s.approvers > 1
                ? `Not in effect: ${s.approvers} people can approve changes, so every change needs a second person.`
                : "In effect: you have one approver.")}
            />
          </ul>
        </Panel>

        <Panel title="Write access per organisation" hint={`${entities.data.filter((e) => e.can_write).length} of ${entities.data.length} can write`}>
          {entities.data.length === 0 ? (
            <p className="px-5 py-6 text-sm text-muted">No organisations connected yet.</p>
          ) : (
            <ul className="divide-y divide-border">
              {entities.data.map((e) => (
                <li key={e.id} className="flex items-center justify-between gap-3 px-5 py-3.5 text-sm">
                  <span className="flex items-center gap-3">
                    <span className="grid h-8 w-8 place-items-center rounded-lg bg-surface-sunken text-muted"><Icon name="building" size={16} /></span>
                    <span className="font-medium">{e.name}</span>
                  </span>
                  {e.can_write ? <Badge tone="emerald" dot>Can write</Badge> : <Badge dot>Read-only</Badge>}
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {isAdmin && s.changes_enabled && entities.data.some((e) => !e.can_write) && (
          <Card padded className="flex flex-wrap items-center gap-4">
            <div className="min-w-0 flex-1 basis-64">
              <p className="font-medium">Grant write access in Xero</p>
              <p className="mt-0.5 text-[13px] text-muted">Xero asks you which organisations to grant, so you can choose just some.</p>
            </div>
            <ButtonLink href={connectUrl(ws, true)} external icon="arrowUpRight">Open Xero</ButtonLink>
          </Card>
        )}
      </div>
    </>
  );
}

function Toggle({ label, help, checked, disabled, onChange, note, icon }: {
  label: string; help: string; checked: boolean; disabled: boolean; onChange: (v: boolean) => void;
  note?: string | false; icon: "changes" | "shield";
}) {
  return (
    <li className={`flex items-start gap-4 px-5 py-5 ${disabled ? "bg-surface-sunken/40" : ""}`}>
      <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-brand-soft text-brand-strong"><Icon name={icon} size={17} /></span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{label}</p>
        <p className="mt-1 text-[13px] leading-relaxed text-muted">{help}</p>
        {note && <p className="mt-2 inline-flex rounded-md bg-surface-sunken px-2 py-1 text-xs font-medium text-foreground/80">{note}</p>}
      </div>
      <Switch checked={checked} disabled={disabled} onChange={onChange} label={label} />
    </li>
  );
}
