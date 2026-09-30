"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { api, connectUrl } from "@/lib/api";
import { useRole } from "@/lib/session";
import { useData } from "@/lib/use-data";
import { Badge, Card, ErrorNote, Loading, PageTitle } from "@/components/ui";

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
        <Card className="mb-4 border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          Writes to Xero are switched off on this server. Changes can be proposed and approved, but nothing will be
          written until an operator turns writes back on.
        </Card>
      )}
      <Card className="divide-y divide-border">
        <Toggle
          label="Allow changes to Xero"
          help="Lets preparers propose, and approvers approve, changes to accounts in connected organisations. Each organisation also needs write access (below)."
          checked={s.changes_enabled} disabled={!isOwner} onChange={(v) => toggle("changes_enabled", v)}
        />
        <Toggle
          label="Allow self-approval"
          help="By default the person who proposes a change can't approve it. Turn this on only for small teams; every self-approved change is flagged in the audit log."
          checked={s.allow_self_approval} disabled={!isOwner || !s.changes_enabled}
          onChange={(v) => toggle("allow_self_approval", v)}
        />
      </Card>
      {!isOwner && <p className="mt-2 text-xs text-muted">Only the workspace owner can change these.</p>}

      <h2 className="mb-2 mt-8 text-sm font-semibold text-slate-900">Write access per organisation</h2>
      <Card className="divide-y divide-border">
        {entities.data.map((e) => (
          <div key={e.id} className="flex items-center justify-between px-4 py-3 text-sm">
            <span className="font-medium text-slate-900">{e.name}</span>
            {e.can_write ? <Badge tone="emerald">can write</Badge> : <Badge>read-only</Badge>}
          </div>
        ))}
      </Card>
      {isAdmin && s.changes_enabled && entities.data.some((e) => !e.can_write) && (
        <div className="mt-3">
          <a href={connectUrl(ws, true)} className="inline-flex rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700">
            Grant write access in Xero
          </a>
          <p className="mt-1 text-xs text-muted">Xero asks you which organisations to grant; you can choose just some.</p>
        </div>
      )}
    </>
  );
}

function Toggle({ label, help, checked, disabled, onChange }: {
  label: string; help: string; checked: boolean; disabled: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className={`flex items-start justify-between gap-6 px-4 py-4 ${disabled ? "opacity-70" : "cursor-pointer"}`}>
      <span>
        <span className="block text-sm font-medium text-slate-900">{label}</span>
        <span className="mt-0.5 block text-xs text-muted">{help}</span>
      </span>
      <input type="checkbox" role="switch" className="mt-1 h-4 w-4 accent-emerald-600" checked={checked}
        disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}
