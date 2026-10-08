import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-xl border border-border bg-surface shadow-sm ${className}`}
    >
      {children}
    </div>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode }[];
}) {
  return (
    <div className="inline-flex w-full rounded-lg bg-surface-sunken p-1 ring-1 ring-inset ring-border">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
            value === o.value
              ? "bg-surface text-brand-strong shadow-sm ring-1 ring-inset ring-border"
              : "text-muted hover:text-slate-700"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  type = "button",
  className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: "primary" | "ghost" | "subtle";
  type?: "button" | "submit";
  className?: string;
}) {
  const styles = {
    primary:
      "bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-slate-300 disabled:text-slate-500",
    ghost:
      "bg-transparent text-slate-700 hover:bg-slate-100 disabled:text-slate-400",
    subtle:
      "bg-slate-900 text-white hover:bg-slate-800 disabled:bg-slate-300 disabled:text-slate-500",
  }[variant];
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {children}
    </button>
  );
}

export function Badge({
  children,
  tone = "slate",
}: {
  children: ReactNode;
  tone?: "slate" | "emerald" | "amber" | "red" | "blue";
}) {
  const tones = {
    slate: "bg-slate-100 text-slate-700 ring-slate-200",
    emerald: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    amber: "bg-amber-50 text-amber-700 ring-amber-200",
    red: "bg-red-50 text-red-700 ring-red-200",
    blue: "bg-blue-50 text-blue-700 ring-blue-200",
  }[tone];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${tones}`}
    >
      {children}
    </span>
  );
}

export function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const tone = value >= 0.85 ? "emerald" : value >= 0.6 ? "amber" : "red";
  return <Badge tone={tone}>{pct}% confident</Badge>;
}

const SYNC_TONES: Record<string, "slate" | "emerald" | "amber" | "red" | "blue"> = {
  never: "slate",
  queued: "blue",
  running: "amber",
  ok: "emerald",
  error: "red",
};

export function SyncBadge({ status }: { status: string }) {
  const label = { never: "not synced", queued: "queued", running: "syncing…", ok: "synced", error: "sync failed" }[status] ?? status;
  return <Badge tone={SYNC_TONES[status] ?? "slate"}>{label}</Badge>;
}

const SOURCE_LABELS: Record<string, string> = {
  exact: "exact match",
  name: "same name",
  code_conflict: "code conflict",
  ai: "AI suggestion",
  manual: "set by a person",
  unmatched: "no match found",
  created: "created by Canopy",
};

export function SourceBadge({ source }: { source: string }) {
  const tone =
    source === "exact" || source === "manual" || source === "created" ? "emerald"
      : source === "code_conflict" || source === "unmatched" ? "amber"
      : "blue";
  return <Badge tone={tone}>{SOURCE_LABELS[source] ?? source}</Badge>;
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {message}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return <p className="py-8 text-center text-sm text-muted">{label}</p>;
}

export function PageTitle({ title, subtitle, action }: { title: string; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

const CHANGE_TONES: Record<string, "slate" | "emerald" | "amber" | "red" | "blue"> = {
  draft: "slate", submitted: "blue", approved: "blue", executing: "amber", completed: "emerald",
  partial: "amber", failed: "red", rejected: "red", cancelled: "slate",
  pending: "slate", running: "amber", succeeded: "emerald", skipped: "slate",
};

export function ChangeBadge({ status }: { status: string }) {
  return <Badge tone={CHANGE_TONES[status] ?? "slate"}>{status}</Badge>;
}

export const OPERATION_LABELS: Record<string, string> = {
  create_account: "Create account",
  update_account: "Edit account",
  archive_account: "Archive account",
  create_tracking_category: "Create tracking category",
  create_tracking_option: "Add tracking option",
  update_tracking_category: "Rename tracking category",
  update_tracking_option: "Rename tracking option",
  archive_tracking_category: "Archive tracking category",
  archive_tracking_option: "Archive tracking option",
};

// Cell states shared by the account and tracking gap matrices.
export const GAP_CELL = {
  mapped: { cls: "bg-emerald-100 text-emerald-800", label: "✓" },
  pending: { cls: "bg-amber-100 text-amber-800", label: "?" },
  gap: { cls: "bg-red-100 text-red-800", label: "✕" },
  no_category: { cls: "bg-slate-100 text-slate-400", label: "–" },
} as const;
