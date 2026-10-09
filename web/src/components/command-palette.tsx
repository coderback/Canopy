"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { Icon, type IconName } from "./icons";
import { Kbd } from "./ui";

export type PaletteItem = { id: string; label: string; hint?: string; icon: IconName; group: string; href?: string; run?: () => void };

/** ⌘K / Ctrl+K quick switcher: jump to any screen or organisation without hunting through the sidebar. */
export function CommandPalette({ open, onClose, items }: { open: boolean; onClose: () => void; items: PaletteItem[] }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((i) => `${i.label} ${i.hint ?? ""} ${i.group}`.toLowerCase().includes(q));
  }, [items, query]);

  useEffect(() => {
    if (open) input.current?.focus();
  }, [open]);

  if (!open) return null;

  function close() {
    setQuery("");
    setCursor(0);
    onClose();
  }

  function choose(item: PaletteItem | undefined) {
    if (!item) return;
    close();
    if (item.run) item.run();
    else if (item.href) router.push(item.href);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") close();
    else if (e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => Math.min(c + 1, results.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); choose(results[cursor]); }
  }

  const groups = [...new Set(results.map((r) => r.group))];

  return (
    <div className="fixed inset-0 z-[60] flex items-start justify-center px-4 pt-[14vh] animate-fade-in" onKeyDown={onKeyDown}>
      <div className="absolute inset-0 bg-ink/35 backdrop-blur-[2px]" onClick={close} />
      <div role="dialog" aria-modal="true" aria-label="Quick switcher"
        className="relative w-full max-w-lg overflow-hidden rounded-2xl border border-border bg-surface shadow-pop animate-pop">
        <div className="flex items-center gap-3 border-b border-border px-4">
          <Icon name="search" size={18} className="text-subtle" />
          <input ref={input} value={query} onChange={(e) => { setQuery(e.target.value); setCursor(0); }}
            placeholder="Jump to a page or organisation…" aria-label="Search"
            className="h-12 flex-1 bg-transparent text-[15px] outline-none placeholder:text-subtle" />
          <Kbd>esc</Kbd>
        </div>
        <div className="canopy-scroll max-h-80 overflow-y-auto p-2">
          {results.length === 0 && <p className="px-3 py-8 text-center text-sm text-muted">Nothing matches “{query}”.</p>}
          {groups.map((g) => (
            <div key={g} className="mb-1">
              <p className="eyebrow px-3 pb-1 pt-2">{g}</p>
              {results.filter((r) => r.group === g).map((r) => {
                const idx = results.indexOf(r);
                const on = idx === cursor;
                return (
                  <button key={r.id} onMouseEnter={() => setCursor(idx)} onClick={() => choose(r)}
                    className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left text-sm ${on ? "bg-brand-soft text-brand-deep" : "text-foreground"}`}>
                    <Icon name={r.icon} size={17} className={on ? "text-brand" : "text-subtle"} />
                    <span className="flex-1 truncate">{r.label}</span>
                    {r.hint && <span className="truncate text-xs text-muted">{r.hint}</span>}
                    {on && <Icon name="arrowRight" size={14} className="text-brand" />}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
        <div className="flex items-center gap-4 border-t border-border bg-surface-sunken/60 px-4 py-2 text-[11px] text-muted">
          <span className="flex items-center gap-1.5"><Kbd>↑</Kbd><Kbd>↓</Kbd> navigate</span>
          <span className="flex items-center gap-1.5"><Kbd>↵</Kbd> open</span>
        </div>
      </div>
    </div>
  );
}
