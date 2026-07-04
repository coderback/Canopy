"use client";

import { useCallback, useEffect, useState } from "react";
import { getEntities, getRun, getRuns, type Entity, type Run } from "@/lib/api";
import { Card } from "@/components/ui";
import ApprovalTable from "@/components/ApprovalTable";
import EntitiesPanel from "@/components/EntitiesPanel";
import NewChangeForm from "@/components/NewChangeForm";
import RunHistory from "@/components/RunHistory";

export default function Home() {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [activeRun, setActiveRun] = useState<Run | null>(null);
  const [connError, setConnError] = useState<string | null>(null);

  const refreshLists = useCallback(async () => {
    try {
      const [e, r] = await Promise.all([getEntities(), getRuns()]);
      setEntities(e);
      setRuns(r);
      setConnError(null);
    } catch (err) {
      setConnError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    refreshLists();
  }, [refreshLists]);

  const onRun = useCallback(
    (run: Run) => {
      setActiveRun(run);
      refreshLists();
    },
    [refreshLists]
  );

  const onSelectRun = useCallback(async (id: number) => {
    try {
      setActiveRun(await getRun(id));
    } catch {
      /* ignore */
    }
  }, []);

  return (
    <div className="min-h-full w-full">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto max-w-6xl px-6 py-5">
          <div className="flex items-center gap-2">
            <span className="text-xl">🌳</span>
            <h1 className="text-lg font-semibold text-slate-900">Canopy</h1>
            <span className="text-sm text-muted">Multi-Entity Command Centre</span>
          </div>
          <p className="mt-1 text-sm text-slate-600">
            One change, propagated correctly across every Xero organisation. The AI proposes and
            explains; a human approves once; deterministic code writes.
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-6">
        {connError && (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
            {connError}
          </div>
        )}

        <Card className="mb-6">
          <EntitiesPanel entities={entities} />
        </Card>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-1">
            <Card>
              <NewChangeForm entities={entities} onRun={onRun} />
            </Card>
            <Card>
              <RunHistory runs={runs} activeId={activeRun?.id ?? null} onSelect={onSelectRun} />
            </Card>
          </div>

          <div className="lg:col-span-2">
            <Card>
              {activeRun ? (
                <ApprovalTable run={activeRun} onRunUpdate={onRun} />
              ) : (
                <div className="flex min-h-64 flex-col items-center justify-center px-6 py-16 text-center">
                  <p className="text-sm font-medium text-slate-700">No run selected</p>
                  <p className="mt-1 max-w-sm text-sm text-muted">
                    Propose a change across your entities, or click <b>Load demo run</b> to see the
                    batched approval flow — including the 200→201 account mapping and a refusal that
                    blocks approval.
                  </p>
                </div>
              )}
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
