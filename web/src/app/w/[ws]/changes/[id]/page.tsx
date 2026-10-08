"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { api, type ChangeItem, type ChangeSet } from "@/lib/api";
import { useRole, useSession } from "@/lib/session";
import { useData } from "@/lib/use-data";
import { Button, Card, ChangeBadge, ErrorNote, Loading, OPERATION_LABELS, PageTitle } from "@/components/ui";

const AUTHORS = ["owner", "admin", "preparer"];
const DECIDERS = ["owner", "admin", "approver"];
const LIVE = new Set(["approved", "executing"]);

export default function ChangePage() {
  const { ws, id } = useParams<{ ws: string; id: string }>();
  const router = useRouter();
  const { me } = useSession();
  const { role } = useRole(ws);
  const change = useData(() => api.change(ws, id), (c: ChangeSet) => LIVE.has(c.status));
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!change.data || !me) return <Loading />;
  const c = change.data;
  const isAuthor = c.author.id === me.user.id;
  const isDecider = DECIDERS.includes(role ?? "");
  const canEdit = c.status === "draft" && (isAuthor || role === "owner" || role === "admin");
  const canDecide = c.status === "submitted" && isDecider && !isAuthor;
  // The API tells the author whether this change qualifies; it enforces the same rules.
  const canSelfApprove = c.status === "submitted" && isAuthor && isDecider && !c.self_approval_blocker;
  const canReview = c.needs_review && isDecider && !isAuthor;
  const canCancel = ["draft", "submitted"].includes(c.status) && (isAuthor || role === "owner" || role === "admin");
  const canRetry = ["partial", "failed"].includes(c.status) && DECIDERS.includes(role ?? "");

  async function act(fn: () => Promise<unknown>, after?: () => void) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await change.reload();
      after?.();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const blocked = (c.items ?? []).filter((i) => i.preflight_status === "blocked").length;

  return (
    <>
      <PageTitle
        title={c.title}
        subtitle={<>Proposed by {c.author.name || c.author.email} · <ChangeBadge status={c.status} />
          {c.self_approved && <> · <b className="text-amber-700">self-approved</b></>}</>}
      />
      {c.reason && <p className="mb-4 text-sm text-slate-700">{c.reason}</p>}
      <ErrorNote message={error ?? change.error} />
      {c.decided_by && (
        <p className="mb-4 text-sm text-muted">
          {c.status === "rejected" ? "Rejected" : c.self_approved ? "Self-approved" : "Approved"} by{" "}
          {c.decided_by.name || c.decided_by.email}
          {c.decision_note && <>: “{c.decision_note}”</>}
        </p>
      )}
      {c.self_approved && (c.reviewed_by ? (
        <p className="mb-4 text-sm text-muted">
          Reviewed by {c.reviewed_by.name || c.reviewed_by.email}
          {c.review_note && <>: “{c.review_note}”</>}
        </p>
      ) : (
        <Card className="mb-4 border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <p>Self-approved: nobody else has looked at this change yet. Someone who can approve changes should review it.</p>
          {canReview && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Review note (optional)"
                aria-label="Review note" className="min-w-64 flex-1 rounded-lg border border-border-strong bg-white px-3 py-2 text-sm" />
              <Button disabled={busy} onClick={() => act(() => api.reviewChange(ws, c.id, note), () => setNote(""))}>
                Mark reviewed
              </Button>
            </div>
          )}
        </Card>
      ))}

      <Card className="divide-y divide-border">
        {(c.items ?? []).map((item) => (
          <Item key={item.id} item={item} editable={canEdit}
            onRemove={() => act(() => api.removeChangeItem(ws, c.id, item.id))}
            onEdit={(payload) => act(() => api.editChangeItem(ws, c.id, item.id, payload))} />
        ))}
        {(c.items ?? []).length === 0 && <p className="p-6 text-sm text-muted">No items.</p>}
      </Card>

      <div className="mt-4 flex flex-wrap items-start gap-2">
        {canEdit && AUTHORS.includes(role ?? "") && (
          <Button disabled={busy || blocked > 0} onClick={() => act(() => api.submitChange(ws, c.id))}>
            {blocked ? `Fix ${blocked} blocked item${blocked === 1 ? "" : "s"} to submit` : "Submit for approval"}
          </Button>
        )}
        {canDecide && (
          <div className="flex w-full flex-wrap items-center gap-2 rounded-lg border border-border bg-surface p-3">
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note (required to reject)"
              aria-label="Decision note" className="min-w-64 flex-1 rounded-lg border border-border-strong px-3 py-2 text-sm" />
            <Button disabled={busy} onClick={() => act(() => api.approveChange(ws, c.id, note || undefined))}>
              Approve and apply
            </Button>
            <Button variant="ghost" disabled={busy || !note.trim()} onClick={() => act(() => api.rejectChange(ws, c.id, note))}>
              Reject
            </Button>
          </div>
        )}
        {canSelfApprove && (
          <div className="w-full rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <p>
              You proposed this change and you&apos;re the only approver, so you can approve it yourself: it only
              brings organisations into line with the group standard. Say why; the change waits in the review queue
              until someone else looks at it.
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why approve it yourself? (required)"
                aria-label="Self-approval note" className="min-w-64 flex-1 rounded-lg border border-border-strong bg-white px-3 py-2 text-sm" />
              <Button disabled={busy || !note.trim()} onClick={() => act(() => api.approveChange(ws, c.id, note))}>
                Approve my own change
              </Button>
            </div>
          </div>
        )}
        {c.status === "submitted" && isAuthor && !canSelfApprove && (
          <p className="w-full text-sm text-muted">
            Waiting for another approver. You can&apos;t approve your own change
            {c.self_approval_blocker ? <>: {c.self_approval_blocker}</> : "."}
          </p>
        )}
        {canRetry && <Button disabled={busy} onClick={() => act(() => api.retryChange(ws, c.id))}>Retry failed items</Button>}
        {canCancel && (
          <Button variant="ghost" disabled={busy} onClick={() => act(() => api.cancelChange(ws, c.id), () => router.push(`/w/${ws}/changes`))}>
            Cancel change
          </Button>
        )}
      </div>
    </>
  );
}

function describe(item: ChangeItem): string {
  const p = item.payload as Record<string, string | undefined>;
  const category = item.tracking_category?.name ?? "(category)";
  const option = `${category} / ${item.tracking_option?.name ?? "(option)"}`;
  switch (item.operation) {
    case "create_tracking_category": {
      const options = (item.payload as { options?: string[] }).options ?? [];
      return `${p.name} · ${options.length ? `options: ${options.join(", ")}` : "no options"}`;
    }
    case "create_tracking_option": return `${category} → new option ${p.name}`;
    case "update_tracking_category": return `${category}: name → ${p.name}`;
    case "update_tracking_option": return `${option}: name → ${p.name}`;
    case "archive_tracking_category": return category;
    case "archive_tracking_option": return option;
  }
  if (item.operation === "create_account") {
    return `${p.code} ${p.name} · ${p.type}${p.tax_type ? ` · tax ${p.tax_type}` : " · Xero's default tax"}`;
  }
  const acct = item.account ? `${item.account.code ?? "—"} ${item.account.name}` : "(account)";
  if (item.operation === "archive_account") return acct;
  const changes = Object.entries(p).map(([k, v]) => `${k} → ${v}`).join(", ");
  return `${acct}: ${changes}`;
}

function Item({ item, editable, onRemove, onEdit }: {
  item: ChangeItem; editable: boolean; onRemove: () => void; onEdit: (payload: Record<string, unknown>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const p = item.payload as Record<string, string | undefined>;
  const [code, setCode] = useState(p.code ?? "");
  const [taxType, setTaxType] = useState(p.tax_type ?? "");

  return (
    <div className="space-y-2 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-slate-900">{item.entity_name}</span>
        <span className="text-muted">· {OPERATION_LABELS[item.operation]}</span>
        <ChangeBadge status={item.status} />
        {item.attempt > 1 && <span className="text-xs text-muted">attempt {item.attempt}</span>}
        {editable && (
          <span className="ml-auto flex gap-1">
            {item.operation === "create_account" && (
              <Button variant="ghost" onClick={() => setEditing((e) => !e)}>{editing ? "Close" : "Edit"}</Button>
            )}
            <Button variant="ghost" onClick={onRemove}>Remove</Button>
          </span>
        )}
      </div>
      <p className="font-mono text-xs text-slate-700">{describe(item)}</p>
      {editing && (
        <div className="flex flex-wrap items-center gap-2">
          <input value={code} onChange={(e) => setCode(e.target.value)} aria-label="Account code" placeholder="Code"
            className="w-28 rounded-lg border border-border-strong px-2 py-1.5" />
          <input value={taxType} onChange={(e) => setTaxType(e.target.value)} aria-label="Tax type" placeholder="Tax type (blank = Xero default)"
            className="w-64 rounded-lg border border-border-strong px-2 py-1.5" />
          <Button onClick={() => { onEdit({ code, tax_type: taxType || null }); setEditing(false); }}>Save</Button>
        </div>
      )}
      {item.preflight_status === "blocked" && item.status === "pending" && (
        <ul className="list-disc pl-5 text-xs text-red-700">
          {item.preflight_messages.map((m, i) => <li key={i}>{m}</li>)}
        </ul>
      )}
      {item.error && <p className="text-xs text-red-700">{item.error}</p>}
      {(item.before || item.after) && (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted">Before / after in Xero</summary>
          <pre className="mt-1 overflow-x-auto rounded bg-surface-sunken p-2 font-mono">
            {JSON.stringify({ before: pick(item.before), after: pick(item.after) }, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

// Show the fields a person cares about, not Xero's whole object.
function pick(a: Record<string, unknown> | null) {
  if (!a) return null;
  const keys = ["Code", "Name", "Type", "TaxType", "Status", "Description"];
  const out: Record<string, unknown> = Object.fromEntries(keys.filter((k) => a[k] !== undefined).map((k) => [k, a[k]]));
  // A tracking category: list its options by name.
  if (Array.isArray(a.Options)) out.Options = (a.Options as { Name?: string }[]).map((o) => o.Name);
  return out;
}
