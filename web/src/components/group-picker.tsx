"use client";

import { useMemo, useState } from "react";
import { Button, Code, Icon, SearchInput, SlideOver } from "./ui";

export type PickerChoice = { id: string; name: string; code?: string | null; meta?: string };

/**
 * Slide-over for choosing which group account/category/option a local one maps to.
 * Searchable, with an explicit "Local only" choice, so a human decision is a couple of clicks.
 */
export function GroupPicker({
  open,
  onClose,
  title,
  subject,
  choices,
  current,
  noun = "group account",
  onSave,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  /** What is being mapped, shown at the top of the panel. */
  subject: React.ReactNode;
  choices: PickerChoice[];
  /** The currently mapped choice id: null = local only, undefined = nothing yet. */
  current?: string | null;
  noun?: string;
  onSave: (choiceId: string | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<string | null | undefined>(current);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? choices.filter((c) => `${c.code ?? ""} ${c.name}`.toLowerCase().includes(q)) : choices;
  }, [choices, query]);

  function save() {
    if (picked === undefined) return;
    onSave(picked);
    onClose();
  }

  return (
    <SlideOver open={open} onClose={onClose} title={title} description={subject}
      footer={
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-muted">
            {picked === undefined ? `Choose a ${noun} or “local only”.` : picked === null ? "Marked as local only." : "Ready to save."}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button disabled={picked === undefined} onClick={save}>Save mapping</Button>
          </div>
        </div>
      }>
      <div className="sticky top-0 z-10 border-b border-border bg-surface px-5 py-3">
        <SearchInput value={query} onChange={setQuery} label={`Search ${noun}s`} placeholder={`Search ${noun}s…`} />
      </div>
      <ul className="p-2.5">
        <li>
          <Choice selected={picked === null} onClick={() => setPicked(null)}>
            <span className="grid h-7 w-7 place-items-center rounded-lg bg-surface-sunken text-muted"><Icon name="lock" size={15} /></span>
            <span className="flex-1">
              <span className="block text-sm font-medium">Local only</span>
              <span className="block text-xs text-muted">No group equivalent. Stays specific to this organisation.</span>
            </span>
          </Choice>
        </li>
        {shown.map((c) => (
          <li key={c.id}>
            <Choice selected={picked === c.id} onClick={() => setPicked(c.id)}>
              {c.code ? <Code>{c.code}</Code> : <span className="grid h-7 w-7 place-items-center rounded-lg bg-brand-soft text-brand-strong"><Icon name="tag" size={14} /></span>}
              <span className="flex-1 truncate text-sm">{c.name}</span>
              {c.meta && <span className="text-[11px] text-subtle">{c.meta}</span>}
            </Choice>
          </li>
        ))}
        {shown.length === 0 && <li className="px-3 py-8 text-center text-sm text-muted">No {noun}s match “{query}”.</li>}
      </ul>
    </SlideOver>
  );
}

function Choice({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} aria-pressed={selected}
      className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
        selected ? "bg-brand-soft ring-1 ring-inset ring-brand/40" : "hover:bg-surface-sunken"}`}>
      {children}
      <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border ${selected ? "border-brand bg-brand text-white" : "border-border-strong"}`}>
        {selected && <Icon name="check" size={12} />}
      </span>
    </button>
  );
}
