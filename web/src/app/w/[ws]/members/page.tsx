"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useRole, useSession } from "@/lib/session";
import { useData } from "@/lib/use-data";
import { Avatar, Badge, Button, Card, ErrorNote, Icon, Input, Loading, Notice, PageTitle, Panel, Select } from "@/components/ui";

const ROLES = ["admin", "preparer", "approver", "viewer"];
const ROLE_HELP: Record<string, string> = {
  owner: "Full control, including settings",
  admin: "Manage the workspace, mappings and members",
  preparer: "Propose changes to Xero",
  approver: "Approve or reject proposed changes",
  viewer: "Read-only access",
};

export default function MembersPage() {
  const { ws } = useParams<{ ws: string }>();
  const { isAdmin } = useRole(ws);
  const { me } = useSession();
  const members = useData(() => api.members(ws));
  const invitations = useData(() => (isAdmin ? api.invitations(ws) : Promise.resolve([])));
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("viewer");
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  if (!members.data) return <Loading />;

  async function run(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await Promise.all([members.reload(), invitations.reload()]);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    await run(async () => {
      const created = await api.invite(ws, email, role);
      setLink(`${window.location.origin}/invite?token=${encodeURIComponent(created.token)}`);
      setCopied(false);
      setEmail("");
    });
  }

  async function copy() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      /* clipboard unavailable: the link is selectable below */
    }
  }

  const pending = invitations.data ?? [];

  return (
    <>
      <PageTitle title="Members" subtitle="Who can see and change this workspace. Preparers propose changes; approvers sign them off." />
      <ErrorNote message={error ?? members.error} />

      <div className="grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Panel title="People" hint={`${members.data.length} ${members.data.length === 1 ? "member" : "members"}`}>
          <ul className="divide-y divide-border">
            {members.data.map((m) => {
              const editable = isAdmin && m.role !== "owner" && m.user_id !== me?.user.id;
              return (
                <li key={m.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3.5 sm:px-5">
                  <Avatar name={m.name || m.email} size={38} />
                  <div className="min-w-0 flex-1 basis-48">
                    <p className="flex items-center gap-2 font-medium">
                      <span className="truncate">{m.name || m.email}</span>
                      {m.user_id === me?.user.id && <Badge>You</Badge>}
                    </p>
                    <p className="truncate text-[13px] text-muted">{m.email}</p>
                  </div>
                  {editable ? (
                    <div className="flex items-center gap-1.5">
                      <Select value={m.role} onChange={(e) => run(() => api.changeRole(ws, m.id, e.target.value))} aria-label={`Role for ${m.email}`} className="h-8 w-32 text-[13px] capitalize">
                        {ROLES.map((r) => <option key={r} value={r}>{r[0].toUpperCase() + r.slice(1)}</option>)}
                      </Select>
                      <Button variant="ghost" size="sm" icon="trash" aria-label={`Remove ${m.email}`} onClick={() => run(() => api.removeMember(ws, m.id))} />
                    </div>
                  ) : (
                    <Badge tone={m.role === "owner" ? "emerald" : "slate"}>{m.role[0].toUpperCase() + m.role.slice(1)}</Badge>
                  )}
                </li>
              );
            })}
          </ul>
        </Panel>

        <div className="space-y-4">
          {isAdmin && (
            <Card padded className="space-y-4">
              <div>
                <h2 className="text-base font-semibold tracking-tight">Invite someone</h2>
                <p className="mt-0.5 text-[13px] text-muted">Create a single-use link for their email address.</p>
              </div>
              <form onSubmit={invite} className="space-y-3">
                <div>
                  <label htmlFor="inv-email" className="mb-1.5 block text-sm font-medium">Email</label>
                  <Input id="inv-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" required />
                </div>
                <div>
                  <label htmlFor="inv-role" className="mb-1.5 block text-sm font-medium">Role</label>
                  <Select id="inv-role" value={role} onChange={(e) => setRole(e.target.value)} className="capitalize">
                    {ROLES.map((r) => <option key={r} value={r}>{r[0].toUpperCase() + r.slice(1)}</option>)}
                  </Select>
                  <p className="mt-1.5 text-xs text-muted">{ROLE_HELP[role]}</p>
                </div>
                <Button type="submit" icon="link" className="w-full" disabled={!email.trim()}>Create invite link</Button>
              </form>
              {link && (
                <Notice tone="good" className="!items-start">
                  <p className="mb-2 text-[13px]">Send this to them. It works once, for that email address, for 7 days.</p>
                  <code className="block break-all rounded-lg bg-white/70 px-2.5 py-2 font-mono text-[11px]">{link}</code>
                  <Button size="sm" variant="outline" className="mt-2.5" icon={copied ? "check" : "file"} onClick={copy}>{copied ? "Copied" : "Copy link"}</Button>
                </Notice>
              )}
            </Card>
          )}

          {isAdmin && pending.length > 0 && (
            <Panel title="Pending invites" hint={`${pending.length}`}>
              <ul className="divide-y divide-border">
                {pending.map((i) => (
                  <li key={i.id} className="flex items-center gap-3 px-4 py-3 text-sm">
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface-sunken text-muted"><Icon name="mail" size={15} /></span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{i.email}</p>
                      <p className="text-xs capitalize text-muted">{i.role} · expires {new Date(i.expires_at).toLocaleDateString()}</p>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => run(() => api.revokeInvitation(ws, i.id))}>Revoke</Button>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      </div>
    </>
  );
}
