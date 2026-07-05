"use client";

import { useState } from "react";
import type { Entity, Run } from "@/lib/api";
import { Segmented } from "./ui";
import NewChangeForm from "./NewChangeForm";
import IngestForm from "./IngestForm";

type Mode = "propagate" | "ingest";

/** The single input surface. Both bounties — propagate a change, or ingest a
 * file — flow through one Compose affordance into one approval surface. */
export default function ComposePanel({
  entities,
  onRun,
}: {
  entities: Entity[];
  onRun: (run: Run) => void;
}) {
  const [mode, setMode] = useState<Mode>("propagate");

  return (
    <div className="p-4">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-sm font-semibold text-slate-900">Compose</h2>
      </div>

      <div className="mb-4">
        <Segmented<Mode>
          value={mode}
          onChange={setMode}
          options={[
            { value: "propagate", label: "Propagate" },
            { value: "ingest", label: "Ingest file" },
          ]}
        />
      </div>

      {mode === "propagate" ? (
        <NewChangeForm entities={entities} onRun={onRun} />
      ) : (
        <IngestForm entities={entities} onRun={onRun} />
      )}
    </div>
  );
}
