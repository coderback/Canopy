"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useRole, useSession } from "@/lib/session";
import { useData } from "@/lib/use-data";
import { Button, Card, ErrorNote, Loading, PageTitle } from "@/components/ui";

const ROLES = ["admin", "preparer", "approver", "viewer"];

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
      setEmail("");
    });
  }

  return (
    <>
      <PageTitle title="Members" subtitle="Preparer and approver roles take effect when change approvals arrive; today they can view." />
      <ErrorNote message={error ?? members.error} />
      <Card className="divide-y divide-border">
        {members.data.map((m) => (
          <div key={m.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
            <div className="flex-1">
              <p className="font-medium text-slate-900">{m.name || m.email}</p>
              <p className="text-muted">{m.email}</p>
            </div>
            {isAdmin && m.role !== "owner" && m.user_id !== me?.user.id ? (
              <>
                <select value={m.role} onChange={(e) => run(() => api.changeRole(ws, m.id, e.target.value))} aria-label={`Role for ${m.email}`}
                  className="rounded-lg border border-border-strong px-2 py-1.5">
                  {ROLES.map((r) => <option key={r}>{r}</option>)}
                </select>
                <Button variant="ghost" onClick={() => run(() => api.removeMember(ws, m.id))}>Remove</Button>
              </>
            ) : (
              <span className="text-muted">{m.role}</span>
            )}
          </div>
        ))}
      </Card>

      {isAdmin && (
        <Card className="mt-6 space-y-3 p-4">
          <h2 className="text-sm font-semibold text-slate-900">Invite someone</h2>
          <form onSubmit={invite} className="flex flex-wrap gap-2">
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" aria-label="Email"
              className="min-w-56 flex-1 rounded-lg border border-border-strong px-3 py-2 text-sm" required />
            <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Role" className="rounded-lg border border-border-strong px-3 py-2 text-sm">
              {ROLES.map((r) => <option key={r}>{r}</option>)}
            </select>
            <Button type="submit">Create invite link</Button>
          </form>
          {link && (
            <div className="rounded-lg bg-surface-sunken p-3 text-sm">
              <p className="mb-1 text-slate-700">Send this link to them. It works once, for that email address, for 7 days:</p>
              <code className="block break-all font-mono text-xs">{link}</code>
            </div>
          )}
          {(invitations.data ?? []).length > 0 && (
            <ul className="divide-y divide-border text-sm">
              {invitations.data!.map((i) => (
                <li key={i.id} className="flex items-center justify-between py-2">
                  <span>{i.email} <span className="text-muted">· {i.role} · expires {new Date(i.expires_at).toLocaleDateString()}</span></span>
                  <Button variant="ghost" onClick={() => run(() => api.revokeInvitation(ws, i.id))}>Revoke</Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </>
  );
}
