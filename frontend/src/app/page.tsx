"use client";

import { useCallback, useEffect, useState } from "react";
import { getEntities, getRun, getRuns, type Entity, type Run } from "@/lib/api";
import { Card } from "@/components/ui";
import ApprovalTable from "@/components/ApprovalTable";
import ComposePanel from "@/components/ComposePanel";
import EntityHealthBar from "@/components/EntityHealthBar";
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
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-border bg-surface/85 backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3 lg:px-6">
          <div className="flex items-center gap-2">
            <span className="text-xl">🌳</span>
            <h1 className="text-base font-semibold text-slate-900">Canopy</h1>
            <span className="hidden text-sm text-muted sm:inline">Multi-Entity Command Centre</span>
          </div>
          <div className="ml-auto">
            <EntityHealthBar entities={entities} />
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6">
        {connError && (
          <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-800">
            {connError}
          </div>
        )}

        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
          <aside className="space-y-4 lg:sticky lg:top-[76px]">
            <Card>
              <ComposePanel entities={entities} onRun={onRun} />
            </Card>
            <Card>
              <RunHistory runs={runs} activeId={activeRun?.id ?? null} onSelect={onSelectRun} />
            </Card>
          </aside>

          <section>
            <Card>
              {activeRun ? (
                <ApprovalTable run={activeRun} onRunUpdate={onRun} />
              ) : (
                <EmptyReview />
              )}
            </Card>
          </section>
        </div>
      </main>
    </div>
  );
}

function EmptyReview() {
  return (
    <div className="flex min-h-[28rem] flex-col items-center justify-center px-6 py-16 text-center">
      <span className="text-3xl">🌳</span>
      <p className="mt-3 text-sm font-medium text-slate-700">Review &amp; approve</p>
      <p className="mt-1 max-w-sm text-sm text-muted">
        Propagate a change or ingest a file from the left. Canopy proposes a mapping per
        organisation and explains it; you approve once; deterministic code writes to Xero.
      </p>
      <div className="mt-4 flex items-center gap-1.5 text-xs text-muted">
        <span className="rounded-full bg-surface-sunken px-2 py-0.5 ring-1 ring-inset ring-border">
          AI proposes
        </span>
        <span>→</span>
        <span className="rounded-full bg-surface-sunken px-2 py-0.5 ring-1 ring-inset ring-border">
          human approves once
        </span>
        <span>→</span>
        <span className="rounded-full bg-surface-sunken px-2 py-0.5 ring-1 ring-inset ring-border">
          code writes
        </span>
      </div>
    </div>
  );
}
