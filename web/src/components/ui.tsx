"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";
import { Icon, type IconName } from "./icons";

export { Icon };

/* ───────────────────────── Surfaces ───────────────────────── */

export function Card({
  children,
  className = "",
  padded = false,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <div className={`rounded-2xl border border-border bg-surface shadow-card ${padded ? "p-5" : ""} ${className}`}>
      {children}
    </div>
  );
}

/** A titled panel in the style of the inspiration dashboards: tinted header strip, white body. */
export function Panel({
  title,
  hint,
  action,
  children,
  className = "",
  bodyClassName = "",
}: {
  title: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`rounded-2xl border border-border bg-surface-sunken/70 p-1.5 shadow-card ${className}`}>
      <header className="flex items-center justify-between gap-3 px-3.5 py-2.5">
        <div className="flex min-w-0 items-baseline gap-2">
          <h2 className="eyebrow !text-[11px] font-medium text-foreground/80">{title}</h2>
          {hint && <span className="truncate text-xs text-subtle">{hint}</span>}
        </div>
        {action}
      </header>
      <div className={`rounded-xl border border-border bg-surface ${bodyClassName}`}>{children}</div>
    </section>
  );
}

export function StatCard({
  label,
  value,
  unit,
  hint,
  tone = "neutral",
  icon,
  href,
  featured = false,
  className = "",
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  hint?: ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad";
  icon?: IconName;
  href?: string;
  featured?: boolean;
  className?: string;
}) {
  const hintTone = { neutral: "text-muted", good: "text-brand-strong", warn: "text-amber-700", bad: "text-red-700" }[tone];
  const body = (
    <div
      className={`group relative flex h-full flex-col justify-between gap-5 overflow-hidden rounded-2xl border p-4 shadow-card transition ${
        featured
          ? "border-brand-deep bg-brand-deep text-white"
          : "border-border bg-surface hover:border-border-strong"
      }`}
    >
      {featured && <div className="dot-grid pointer-events-none absolute inset-0 opacity-60" />}
      <div className="relative flex items-center justify-between">
        <span className={`eyebrow ${featured ? "!text-emerald-200/80" : ""}`}>{label}</span>
        {icon && (
          <span className={`grid h-7 w-7 place-items-center rounded-lg ${featured ? "bg-white/10 text-emerald-200" : "bg-surface-sunken text-muted"}`}>
            <Icon name={icon} size={15} />
          </span>
        )}
      </div>
      <div className="relative">
        <p className="flex items-baseline gap-1.5">
          <span className="tnum text-[28px] font-semibold leading-none tracking-tight">{value}</span>
          {unit && <span className={`text-sm ${featured ? "text-emerald-100/70" : "text-muted"}`}>{unit}</span>}
        </p>
        {hint && <p className={`mt-2 text-xs ${featured ? "text-emerald-100/80" : hintTone}`}>{hint}</p>}
      </div>
    </div>
  );
  return href ? (
    <Link href={href} className={`block rounded-2xl focus-visible:outline-offset-4 ${className}`}>
      {body}
    </Link>
  ) : (
    <div className={className}>{body}</div>
  );
}

/* ───────────────────────── Navigation / controls ───────────────────────── */

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  className = "",
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode; count?: number }[];
  className?: string;
}) {
  return (
    <div role="tablist" className={`inline-flex rounded-xl bg-surface-sunken p-1 ring-1 ring-inset ring-border ${className}`}>
      {options.map((o) => {
        const on = value === o.value;
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={on}
            onClick={() => onChange(o.value)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
              on ? "bg-surface text-foreground shadow-sm ring-1 ring-inset ring-border" : "text-muted hover:text-foreground"
            }`}
          >
            {o.label}
            {o.count !== undefined && (
              <span className={`tnum rounded-full px-1.5 text-[11px] leading-5 ${on ? "bg-brand-soft text-brand-strong" : "bg-border/70 text-muted"}`}>
                {o.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Underline tabs for switching sections within a page. */
export function Tabs<T extends string>({
  value,
  onChange,
  options,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode; count?: number; icon?: IconName }[];
}) {
  return (
    <div role="tablist" className="flex gap-1 border-b border-border">
      {options.map((o) => {
        const on = value === o.value;
        return (
          <button
            key={o.value}
            role="tab"
            aria-selected={on}
            onClick={() => onChange(o.value)}
            className={`-mb-px inline-flex items-center gap-2 border-b-2 px-3 pb-2.5 pt-1 text-sm font-medium transition ${
              on ? "border-brand text-foreground" : "border-transparent text-muted hover:text-foreground"
            }`}
          >
            {o.icon && <Icon name={o.icon} size={16} className={on ? "text-brand" : ""} />}
            {o.label}
            {o.count !== undefined && (
              <span className={`tnum rounded-full px-1.5 text-[11px] leading-5 ${on ? "bg-brand-soft text-brand-strong" : "bg-border/70 text-muted"}`}>
                {o.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

type ButtonVariant = "primary" | "dark" | "outline" | "ghost" | "danger" | "subtle";
type ButtonSize = "sm" | "md";

const BUTTON_STYLES: Record<ButtonVariant, string> = {
  primary: "bg-brand text-white shadow-sm hover:bg-brand-strong disabled:bg-border-strong disabled:text-white/80 disabled:shadow-none",
  dark: "bg-ink text-white shadow-sm hover:bg-black disabled:bg-border-strong disabled:text-white/80 disabled:shadow-none",
  // `subtle` kept for backwards compatibility: it was the dark button.
  subtle: "bg-ink text-white shadow-sm hover:bg-black disabled:bg-border-strong disabled:text-white/80 disabled:shadow-none",
  outline: "border border-border-strong bg-surface text-foreground shadow-sm hover:bg-surface-hover disabled:text-subtle disabled:shadow-none",
  ghost: "text-muted hover:bg-surface-sunken hover:text-foreground disabled:text-subtle disabled:hover:bg-transparent",
  danger: "border border-red-200 bg-red-50 text-red-700 hover:bg-red-100 disabled:opacity-50",
};
const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-8 gap-1.5 rounded-lg px-3 text-[13px]",
  md: "h-9 gap-2 rounded-[10px] px-4 text-sm",
};
const buttonClass = (variant: ButtonVariant, size: ButtonSize, extra = "") =>
  `inline-flex shrink-0 items-center justify-center whitespace-nowrap font-medium transition-colors disabled:cursor-not-allowed ${BUTTON_STYLES[variant]} ${BUTTON_SIZES[size]} ${extra}`;

export function Button({
  children,
  onClick,
  disabled,
  variant = "primary",
  size = "md",
  icon,
  type = "button",
  className = "",
  ...rest
}: {
  children?: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  type?: "button" | "submit";
  className?: string;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick" | "type" | "className" | "children" | "disabled">) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={buttonClass(variant, size, className)} {...rest}>
      {icon && <Icon name={icon} size={size === "sm" ? 15 : 16} />}
      {children}
    </button>
  );
}

/** A link that looks like a button (navigations, OAuth redirects). */
export function ButtonLink({
  href,
  children,
  variant = "primary",
  size = "md",
  icon,
  className = "",
  external = false,
}: {
  href: string;
  children: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  className?: string;
  /** Use a plain <a> (full-page navigation, e.g. OAuth redirects or file downloads). */
  external?: boolean;
}) {
  const cls = buttonClass(variant, size, className);
  const inner = (
    <>
      {icon && <Icon name={icon} size={size === "sm" ? 15 : 16} />}
      {children}
    </>
  );
  return external ? (
    <a href={href} className={cls}>{inner}</a>
  ) : (
    <Link href={href} className={cls}>{inner}</Link>
  );
}

export const inputCls =
  "h-9 rounded-[10px] border border-border-strong bg-surface px-3 text-sm text-foreground shadow-sm placeholder:text-subtle transition focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand-ring/40 disabled:bg-surface-sunken disabled:text-subtle";

export function Input({ className = "", ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`${inputCls} ${/\bw-/.test(className) ? "" : "w-full"} ${className}`} {...rest} />;
}

export function Select({ className = "", children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={`${inputCls} ${/\bw-/.test(className) ? "" : "w-full"} appearance-none bg-[length:16px] bg-[right_10px_center] bg-no-repeat pr-8 ${className}`}
      style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%238a938a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")" }}
      {...rest}>
      {children}
    </select>
  );
}

export function SearchInput({
  value,
  onChange,
  placeholder = "Search…",
  className = "",
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
  label: string;
}) {
  return (
    <div className={`relative ${className}`}>
      <Icon name="search" size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-subtle" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={label}
        className={`${inputCls} w-full pl-9`}
      />
    </div>
  );
}

export function Switch({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
        checked ? "bg-brand" : "bg-border-strong"
      }`}
    >
      <span
        className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${checked ? "translate-x-5" : ""}`}
      />
    </button>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded-md border border-border-strong bg-surface px-1 font-mono text-[10px] text-muted">
      {children}
    </kbd>
  );
}

/* ───────────────────────── Status ───────────────────────── */

type Tone = "slate" | "emerald" | "amber" | "red" | "blue";

const TONES: Record<Tone, { chip: string; dot: string }> = {
  slate: { chip: "bg-slate-100 text-slate-700 ring-slate-200", dot: "bg-slate-400" },
  emerald: { chip: "bg-emerald-50 text-emerald-800 ring-emerald-200", dot: "bg-emerald-500" },
  amber: { chip: "bg-amber-50 text-amber-800 ring-amber-200", dot: "bg-amber-500" },
  red: { chip: "bg-red-50 text-red-700 ring-red-200", dot: "bg-red-500" },
  blue: { chip: "bg-blue-50 text-blue-700 ring-blue-200", dot: "bg-blue-500" },
};

export function Badge({
  children,
  tone = "slate",
  dot = false,
  pulse = false,
}: {
  children: ReactNode;
  tone?: Tone;
  dot?: boolean;
  pulse?: boolean;
}) {
  const t = TONES[tone];
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${t.chip}`}>
      {dot && (
        <span className="relative flex h-1.5 w-1.5">
          {pulse && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${t.dot}`} />}
          <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${t.dot}`} />
        </span>
      )}
      {children}
    </span>
  );
}

/** Confidence as a tiny meter plus a number: scannable down a long list. */
export function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const tone = value >= 0.85 ? "bg-emerald-500" : value >= 0.6 ? "bg-amber-500" : "bg-red-500";
  const text = value >= 0.85 ? "text-emerald-800" : value >= 0.6 ? "text-amber-800" : "text-red-700";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium" title={`${pct}% confidence`}>
      <span className="h-1.5 w-10 overflow-hidden rounded-full bg-border">
        <span className={`block h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </span>
      <span className={`tnum ${text}`}>{pct}%</span>
    </span>
  );
}

const SYNC: Record<string, { tone: Tone; label: string; pulse?: boolean }> = {
  never: { tone: "slate", label: "Not synced" },
  queued: { tone: "blue", label: "Queued", pulse: true },
  running: { tone: "amber", label: "Syncing", pulse: true },
  ok: { tone: "emerald", label: "Synced" },
  error: { tone: "red", label: "Sync failed" },
};

export function SyncBadge({ status }: { status: string }) {
  const s = SYNC[status] ?? { tone: "slate" as Tone, label: status };
  return <Badge tone={s.tone} dot pulse={s.pulse}>{s.label}</Badge>;
}

const SOURCE_LABELS: Record<string, string> = {
  exact: "Exact match",
  name: "Same name",
  code_conflict: "Code conflict",
  ai: "AI suggestion",
  manual: "Set by a person",
  unmatched: "No match found",
  created: "Created by Canopy",
};

export function SourceBadge({ source }: { source: string }) {
  const tone: Tone =
    source === "exact" || source === "manual" || source === "created" ? "emerald"
      : source === "code_conflict" || source === "unmatched" ? "amber"
      : "blue";
  return (
    <Badge tone={tone}>
      {source === "ai" && <Icon name="sparkle" size={12} />}
      {SOURCE_LABELS[source] ?? source}
    </Badge>
  );
}

const CHANGE_TONES: Record<string, Tone> = {
  draft: "slate", submitted: "blue", approved: "blue", executing: "amber", completed: "emerald",
  partial: "amber", failed: "red", rejected: "red", cancelled: "slate",
  pending: "slate", running: "amber", succeeded: "emerald", skipped: "slate",
};

const CHANGE_LABELS: Record<string, string> = {
  draft: "Draft", submitted: "Awaiting approval", approved: "Approved", executing: "Applying",
  completed: "Applied", partial: "Partly applied", failed: "Failed", rejected: "Rejected", cancelled: "Cancelled",
  pending: "Pending", running: "Running", succeeded: "Done", skipped: "Skipped",
};

export function ChangeBadge({ status }: { status: string }) {
  return (
    <Badge tone={CHANGE_TONES[status] ?? "slate"} dot pulse={status === "executing" || status === "running"}>
      {CHANGE_LABELS[status] ?? status}
    </Badge>
  );
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
  mapped: { cls: "bg-emerald-500 text-white", soft: "bg-emerald-100 text-emerald-800", label: "✓", name: "Mapped" },
  pending: { cls: "bg-amber-300 text-amber-950", soft: "bg-amber-100 text-amber-800", label: "?", name: "Suggested, awaiting review" },
  gap: { cls: "bg-red-100 text-red-700 ring-1 ring-inset ring-red-200", soft: "bg-red-100 text-red-700", label: "✕", name: "Gap" },
  no_category: { cls: "bg-slate-100 text-slate-400", soft: "bg-slate-100 text-slate-400", label: "–", name: "Category not in this organisation" },
} as const;

/* ───────────────────────── Progress ───────────────────────── */

export function ProgressRing({
  value,
  size = 44,
  stroke = 5,
  label,
  tone = "brand",
}: {
  value: number; // 0..1
  size?: number;
  stroke?: number;
  label?: ReactNode;
  tone?: "brand" | "amber" | "red";
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  const color = { brand: "var(--brand)", amber: "#f59e0b", red: "#ef4444" }[tone];
  return (
    <span className="relative inline-grid place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - v)} style={{ transition: "stroke-dashoffset 600ms ease" }} />
      </svg>
      <span className="tnum absolute text-[11px] font-semibold">{label ?? `${Math.round(v * 100)}%`}</span>
    </span>
  );
}

export function ProgressBar({ value, tone = "brand", className = "" }: { value: number; tone?: "brand" | "amber" | "red"; className?: string }) {
  const color = { brand: "bg-brand", amber: "bg-amber-500", red: "bg-red-500" }[tone];
  return (
    <div className={`h-1.5 overflow-hidden rounded-full bg-border ${className}`} role="progressbar" aria-valuenow={Math.round(value * 100)} aria-valuemin={0} aria-valuemax={100}>
      <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </div>
  );
}

/* ───────────────────────── Feedback ───────────────────────── */

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div role="alert" className="mb-4 flex items-start gap-2.5 rounded-xl border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-800 animate-fade-in">
      <Icon name="alert" size={17} className="mt-0.5 text-red-600" />
      <span>{message}</span>
    </div>
  );
}

export function Notice({
  children,
  tone = "info",
  action,
  className = "",
}: {
  children: ReactNode;
  tone?: "info" | "warn" | "good";
  action?: ReactNode;
  className?: string;
}) {
  const s = {
    info: "border-blue-200 bg-blue-50 text-blue-900",
    warn: "border-amber-200 bg-amber-50 text-amber-900",
    good: "border-emerald-200 bg-emerald-50 text-emerald-900",
  }[tone];
  const icon: IconName = tone === "warn" ? "alert" : tone === "good" ? "check" : "info";
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border px-3.5 py-2.5 text-sm ${s} ${className}`}>
      <Icon name={icon} size={17} />
      <div className="min-w-0 flex-1 basis-56">{children}</div>
      {action}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="space-y-4 py-2" role="status" aria-label={label}>
      <div className="skeleton h-8 w-56" />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-[104px]" />)}
      </div>
      <div className="skeleton h-72" />
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function EmptyState({
  icon = "tree",
  title,
  children,
  action,
}: {
  icon?: IconName;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      <span className="mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-brand-soft text-brand-strong">
        <Icon name={icon} size={22} />
      </span>
      <h3 className="text-[15px] font-semibold">{title}</h3>
      {children && <p className="mt-1.5 max-w-md text-sm leading-relaxed text-muted">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/* ───────────────────────── Page chrome ───────────────────────── */

export function PageTitle({
  title,
  subtitle,
  action,
  back,
  badge,
}: {
  title: string;
  subtitle?: ReactNode;
  action?: ReactNode;
  back?: { href: string; label: string };
  badge?: ReactNode;
}) {
  return (
    <div className="mb-6 animate-rise">
      {back && (
        <Link href={back.href} className="mb-3 inline-flex items-center gap-1.5 text-[13px] text-muted transition hover:text-foreground">
          <Icon name="arrowLeft" size={14} /> {back.label}
        </Link>
      )}
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-[26px] font-semibold leading-tight tracking-tight">{title}</h1>
            {badge}
          </div>
          {subtitle && <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-muted">{subtitle}</p>}
        </div>
        {action && <div className="flex flex-wrap items-center gap-2">{action}</div>}
      </div>
    </div>
  );
}

export function SectionTitle({ title, hint, action }: { title: string; hint?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-base font-semibold tracking-tight">{title}</h2>
        {hint && <p className="mt-0.5 text-[13px] text-muted">{hint}</p>}
      </div>
      {action}
    </div>
  );
}

export function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  const initials = name.split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase()).join("") || "?";
  const hues = ["#047857", "#0f766e", "#1d4ed8", "#7c3aed", "#b45309", "#be123c"];
  const hue = hues[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % hues.length];
  return (
    <span className="inline-grid shrink-0 place-items-center rounded-full font-semibold text-white"
      style={{ width: size, height: size, background: hue, fontSize: size * 0.38 }} aria-hidden="true">
      {initials}
    </span>
  );
}

/** Account-code chip in monospace, used wherever a code is shown. */
export function Code({ children }: { children: ReactNode }) {
  return <span className="tnum rounded-md bg-surface-sunken px-1.5 py-0.5 font-mono text-[12px] text-muted ring-1 ring-inset ring-border">{children}</span>;
}

/* ───────────────────────── Slide-over ───────────────────────── */

export function SlideOver({
  open,
  onClose,
  title,
  description,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      prev?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 animate-fade-in">
      <div className="absolute inset-0 bg-ink/30 backdrop-blur-[2px]" onClick={onClose} />
      <div
        ref={panel}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="absolute right-0 top-0 flex h-full w-full max-w-md animate-slide-in flex-col bg-surface shadow-pop outline-none"
      >
        <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div className="min-w-0">
            <h2 className="text-base font-semibold tracking-tight">{title}</h2>
            {description && <p className="mt-0.5 text-[13px] text-muted">{description}</p>}
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 text-muted transition hover:bg-surface-sunken hover:text-foreground">
            <Icon name="x" size={18} />
          </button>
        </header>
        <div className="canopy-scroll min-h-0 flex-1 overflow-y-auto">{children}</div>
        {footer && <footer className="border-t border-border bg-surface-sunken/50 px-5 py-3">{footer}</footer>}
      </div>
    </div>
  );
}

/** Sticky bar that appears at the bottom of the screen while something is selected. */
export function ActionBar({ show, children }: { show: boolean; children: ReactNode }) {
  if (!show) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-30 flex justify-center px-4">
      <div className="pointer-events-auto flex flex-wrap items-center gap-3 rounded-2xl border border-white/10 bg-ink px-4 py-2.5 text-sm text-white shadow-pop animate-pop">
        {children}
      </div>
    </div>
  );
}

/* ───────────────────────── Overflow menu ───────────────────────── */

export function Menu({
  items,
  label = "More actions",
}: {
  items: { label: string; onClick: () => void; icon?: IconName; danger?: boolean }[];
  label?: string;
}) {
  const [open, setOpen] = useState(false);
  if (items.length === 0) return null;
  return (
    <div className="relative">
      <button onClick={() => setOpen((o) => !o)} aria-label={label} aria-haspopup="menu" aria-expanded={open}
        className="grid h-8 w-8 place-items-center rounded-lg text-muted transition hover:bg-surface-sunken hover:text-foreground">
        <Icon name="dots" size={18} strokeWidth={3} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <ul role="menu" className="absolute right-0 top-full z-20 mt-1 min-w-56 overflow-hidden rounded-xl border border-border bg-surface p-1 shadow-pop animate-pop">
            {items.map((i) => (
              <li key={i.label}>
                <button role="menuitem" onClick={() => { setOpen(false); i.onClick(); }}
                  className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition hover:bg-surface-sunken ${i.danger ? "text-red-700" : ""}`}>
                  {i.icon && <Icon name={i.icon} size={15} className={i.danger ? "" : "text-muted"} />}
                  {i.label}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
