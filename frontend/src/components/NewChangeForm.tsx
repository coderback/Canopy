"use client";

import { useEffect, useState } from "react";
import {
  createChange,
  seedDemo,
  type ChangeType,
  type DriftPrefill,
  type Entity,
  type Run,
} from "@/lib/api";
import { Button } from "./ui";

const PREFILLS: Record<ChangeType, string> = {
  item: JSON.stringify(
    {
      Code: "TRAMP-SOCK",
      Name: "Trampoline Grip Socks",
      IsSold: true,
      SalesDetails: { UnitPrice: 3.5, AccountCode: "200", TaxType: "OUTPUT2" },
    },
    null,
    2
  ),
  account: JSON.stringify({ Code: "492", Name: "Software Subscriptions", Type: "EXPENSE" }, null, 2),
  contact: JSON.stringify(
    { Name: "Acme Corp", EmailAddress: "ap@acme.example", IsSupplier: true },
    null,
    2
  ),
  tracking: JSON.stringify({ Name: "Region", Options: ["North", "South"] }, null, 2),
};

const TYPES: { value: ChangeType; label: string }[] = [
  { value: "item", label: "Item" },
  { value: "account", label: "Account code" },
  { value: "contact", label: "Contact" },
  { value: "tracking", label: "Tracking" },
];

export default function NewChangeForm({
  entities,
  onRun,
  prefill,
}: {
  entities: Entity[];
  onRun: (run: Run) => void;
  prefill?: DriftPrefill | null;
}) {
  const [changeType, setChangeType] = useState<ChangeType>("item");
  const [payloadText, setPayloadText] = useState(PREFILLS.item);
  const [selected, setSelected] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fromDrift, setFromDrift] = useState(false);

  // Apply a drift-resolution prefill: set type, payload and the single target
  // org, then let the user review before proposing. `nonce` re-triggers on
  // repeat clicks of the same code.
  useEffect(() => {
    if (!prefill) return;
    setChangeType(prefill.changeType);
    setPayloadText(JSON.stringify(prefill.payload, null, 2));
    setSelected([prefill.targetId]);
    setFromDrift(true);
    setError(null);
  }, [prefill]);

  function pickType(t: ChangeType) {
    setChangeType(t);
    setPayloadText(PREFILLS[t]);
    setFromDrift(false);
  }

  function toggle(id: number) {
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  }

  async function submit() {
    setError(null);
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(payloadText);
    } catch {
      setError("Payload is not valid JSON.");
      return;
    }
    if (selected.length === 0) {
      setError("Pick at least one target entity.");
      return;
    }
    setBusy(true);
    try {
      const run = await createChange({ change_type: changeType, payload, target_entity_ids: selected });
      onRun(run);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function loadDemo() {
    setError(null);
    setBusy(true);
    try {
      onRun(await seedDemo());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <p className="mb-3 text-xs text-muted">
        Change a contact, item, account code or tracking category once — Canopy maps it to each
        organisation&apos;s own chart and fans out the writes.
      </p>

      {fromDrift && (
        <div className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800">
          Resolving a detected drift — review the account below, then <b>Propose</b>. Canopy
          maps it to the target org and flags anything unsafe (e.g. a same-named account under a
          different code) for review before any write.
        </div>
      )}

      <div className="mb-3 inline-flex flex-wrap gap-1 rounded-lg bg-surface-sunken p-1 ring-1 ring-inset ring-border">
        {TYPES.map((t) => (
          <button
            key={t.value}
            onClick={() => pickType(t.value)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${
              changeType === t.value ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <textarea
        value={payloadText}
        onChange={(e) => setPayloadText(e.target.value)}
        spellCheck={false}
        rows={9}
        className="w-full rounded-lg border border-border bg-slate-50 p-3 font-mono text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-200"
      />

      <div className="mt-3">
        <p className="mb-1.5 text-xs font-medium text-slate-500">Target entities</p>
        {entities.length === 0 ? (
          <p className="text-xs text-muted">
            No entities connected. Use <b>Load demo run</b> above, or connect Xero orgs.
          </p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {entities.map((e) => (
              <button
                key={e.id}
                onClick={() => toggle(e.id)}
                className={`rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${
                  selected.includes(e.id)
                    ? "bg-blue-600 text-white ring-blue-600"
                    : "bg-white text-slate-600 ring-slate-200 hover:bg-slate-50"
                }`}
              >
                {e.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}

      <div className="mt-3 flex items-center gap-2">
        <Button onClick={submit} disabled={busy || entities.length === 0}>
          {busy ? "Mapping…" : "Propose across entities"}
        </Button>
        <Button variant="ghost" onClick={loadDemo} disabled={busy} className="!px-2.5 !py-2 text-xs">
          Load demo run
        </Button>
      </div>
    </div>
  );
}
