"use client";

import { useMemo, useState } from "react";
import { approveRun, type Proposal, type Run, type RowDecision } from "@/lib/api";
import { Badge, Button, ConfidenceBadge, StatusPill } from "./ui";

type Decision = "include" | "exclude";

function defaultDecision(p: Proposal): Decision | undefined {
  if (p.status === "excluded") return "exclude";
  if (p.needs_human) return undefined; // must be decided explicitly
  return "include";
}

function ResultLine({ p }: { p: Proposal }) {
  const r = p.results[p.results.length - 1];
  if (!r) return null;
  return r.success ? (
    <Badge tone="emerald">written · {r.xero_id ?? "ok"}</Badge>
  ) : (
    <Badge tone="red">failed · {r.error?.slice(0, 60) ?? "error"}</Badge>
  );
}

function ProposalRow({
  p,
  locked,
  decision,
  onDecision,
  edited,
  onEdit,
}: {
  p: Proposal;
  locked: boolean;
  decision: Decision | undefined;
  onDecision: (d: Decision) => void;
  edited: string;
  onEdit: (text: string) => void;
}) {
  const [open, setOpen] = useState(false);
  let jsonError: string | null = null;
  try {
    JSON.parse(edited);
  } catch (e) {
    jsonError = (e as Error).message;
  }

  return (
    <div
      className={`px-4 py-3 ${
        p.needs_human && decision === undefined ? "bg-amber-50/60" : ""
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-slate-900">{p.entity_name}</span>
        <Badge tone="slate">{p.action}</Badge>
        <ConfidenceBadge value={p.confidence} />
        {p.needs_human && <Badge tone="amber">needs review</Badge>}
        <div className="ml-auto flex items-center gap-2">
          {p.results.length > 0 && <ResultLine p={p} />}
          {!locked && (
            <div className="inline-flex overflow-hidden rounded-lg ring-1 ring-inset ring-slate-200">
              <button
                onClick={() => onDecision("include")}
                className={`px-3 py-1 text-xs font-medium ${
                  decision === "include"
                    ? "bg-emerald-600 text-white"
                    : "bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                Include
              </button>
              <button
                onClick={() => onDecision("exclude")}
                className={`px-3 py-1 text-xs font-medium ${
                  decision === "exclude"
                    ? "bg-slate-700 text-white"
                    : "bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                Exclude
              </button>
            </div>
          )}
        </div>
      </div>

      <p className="mt-1.5 text-sm text-slate-600">{p.reasoning}</p>

      <button
        onClick={() => setOpen((v) => !v)}
        className="mt-2 text-xs font-medium text-blue-600 hover:underline"
      >
        {open ? "Hide payload" : "View / edit payload"}
      </button>
      {open && (
        <div className="mt-2">
          <textarea
            value={edited}
            onChange={(e) => onEdit(e.target.value)}
            readOnly={locked}
            spellCheck={false}
            rows={Math.min(12, edited.split("\n").length + 1)}
            className={`w-full rounded-lg border bg-slate-50 p-3 font-mono text-xs text-slate-800 focus:outline-none focus:ring-2 ${
              jsonError ? "border-red-300 focus:ring-red-200" : "border-border focus:ring-blue-200"
            }`}
          />
          {jsonError && !locked && (
            <p className="mt-1 text-xs text-red-600">Invalid JSON — fix before approving.</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function ApprovalTable({
  run,
  onRunUpdate,
}: {
  run: Run;
  onRunUpdate: (run: Run) => void;
}) {
  const proposals = run.proposals ?? [];
  const [decisions, setDecisions] = useState<Record<number, Decision | undefined>>(() =>
    Object.fromEntries(proposals.map((p) => [p.id, defaultDecision(p)]))
  );
  const [edits, setEdits] = useState<Record<number, string>>(() =>
    Object.fromEntries(
      proposals.map((p) => [p.id, JSON.stringify(p.edited_payload ?? p.mapped_payload, null, 2)])
    )
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canApprove = ["proposed", "partial", "failed"].includes(run.status);
  const locked = !canApprove;

  const undecided = proposals.filter((p) => p.needs_human && decisions[p.id] === undefined);
  const anyJsonBroken = proposals.some((p) => {
    try {
      JSON.parse(edits[p.id]);
      return false;
    } catch {
      return true;
    }
  });
  const includedCount = proposals.filter((p) => decisions[p.id] === "include").length;

  const highConf = proposals.filter((p) => !p.needs_human);
  const review = proposals.filter((p) => p.needs_human);

  async function onApprove() {
    setSubmitting(true);
    setError(null);
    try {
      const payloadDecisions: RowDecision[] = proposals.map((p) => {
        const approved = decisions[p.id] === "include";
        const editedObj = JSON.parse(edits[p.id]);
        const changed = JSON.stringify(editedObj) !== JSON.stringify(p.mapped_payload);
        return {
          proposal_id: p.id,
          approved,
          edited_payload: approved && changed ? editedObj : null,
        };
      });
      const updated = await approveRun(run.id, payloadDecisions);
      onRunUpdate(updated);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  function group(list: Proposal[]) {
    return list.map((p) => (
      <ProposalRow
        key={p.id}
        p={p}
        locked={locked}
        decision={decisions[p.id]}
        onDecision={(d) => setDecisions((s) => ({ ...s, [p.id]: d }))}
        edited={edits[p.id]}
        onEdit={(text) => setEdits((s) => ({ ...s, [p.id]: text }))}
      />
    ));
  }

  return (
    <div>
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-slate-900">
            Run #{run.id} · {run.change_type}
          </h2>
          <StatusPill status={run.status} />
        </div>
        <span className="text-xs text-muted">
          {proposals.length} entities · {includedCount} to write
        </span>
      </div>

      <div className="divide-y divide-border">
        {highConf.length > 0 && (
          <div>
            <p className="bg-slate-50 px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              High confidence
            </p>
            <div className="divide-y divide-border">{group(highConf)}</div>
          </div>
        )}
        {review.length > 0 && (
          <div>
            <p className="bg-amber-50 px-4 py-1.5 text-xs font-semibold uppercase tracking-wide text-amber-700">
              Needs a human · {undecided.length} undecided
            </p>
            <div className="divide-y divide-border">{group(review)}</div>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3">
        <div className="text-xs text-muted">
          {locked ? (
            <>Executed — see per-row results above. The LLM proposed; a human approved; code wrote.</>
          ) : undecided.length > 0 ? (
            <span className="text-amber-700">
              {undecided.length} row{undecided.length > 1 ? "s" : ""} flagged <b>needs review</b> —
              include or exclude {undecided.length > 1 ? "each" : "it"} to continue.
            </span>
          ) : anyJsonBroken ? (
            <span className="text-red-600">Fix invalid JSON in an edited payload to continue.</span>
          ) : (
            <>Ready — approve once and Canopy fans the writes out per entity.</>
          )}
        </div>
        {error && <span className="text-xs text-red-600">{error}</span>}
        {!locked && (
          <Button
            onClick={onApprove}
            disabled={submitting || undecided.length > 0 || anyJsonBroken || includedCount === 0}
          >
            {submitting ? "Propagating…" : `Approve & propagate (${includedCount})`}
          </Button>
        )}
      </div>
    </div>
  );
}
