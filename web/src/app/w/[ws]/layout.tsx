"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api, connectUrl, type Entity } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useData } from "@/lib/use-data";
import { Avatar, Kbd, Loading } from "@/components/ui";
import { CanopyMark, Icon, type IconName } from "@/components/icons";
import { CommandPalette, type PaletteItem } from "@/components/command-palette";

type NavItem = { href: string; label: string; icon: IconName; adminOnly?: boolean; badge?: number };

const SYNC_DOT: Record<string, string> = {
  ok: "bg-emerald-500",
  running: "bg-amber-400 animate-pulse",
  queued: "bg-blue-400 animate-pulse",
  error: "bg-red-500",
  never: "bg-slate-300",
};

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { ws, entity } = useParams<{ ws: string; entity?: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const { me, loading, refresh } = useSession();
  // The drawer is open for one specific path, so navigating closes it without an effect.
  const [drawerPath, setDrawerPath] = useState<string | null>(null);
  const drawer = drawerPath === pathname;
  const setDrawer = (open: boolean) => setDrawerPath(open ? pathname : null);
  const [palette, setPalette] = useState(false);
  const [switcher, setSwitcher] = useState(false);

  const membership = me?.workspaces.find((w) => w.id === ws);
  const isAdmin = membership?.role === "owner" || membership?.role === "admin";
  const signedIn = !!me && !!membership;
  const entities = useData(() => (signedIn ? api.entities(ws) : Promise.resolve([] as Entity[])),
    (list: Entity[]) => list.some((e) => e.sync_status === "queued" || e.sync_status === "running"));
  const review = useData(() => (signedIn ? api.changes(ws, true) : Promise.resolve([])));

  useEffect(() => {
    if (!loading && !me) router.replace("/");
  }, [loading, me, router]);

  // The sidebar data can't load until the session has; fetch it once it does.
  const { reload: reloadEntities } = entities;
  const { reload: reloadReview } = review;
  useEffect(() => {
    if (signedIn) {
      reloadEntities();
      reloadReview();
    }
  }, [signedIn, reloadEntities, reloadReview]);

  // ⌘K / Ctrl+K opens the quick switcher.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const base = `/w/${ws}`;
  const orgs = useMemo(() => entities.data ?? [], [entities.data]);
  const reviewCount = review.data?.length ?? 0;

  const paletteItems = useMemo<PaletteItem[]>(() => {
    const pages: PaletteItem[] = [
      { id: "overview", label: "Overview", icon: "home", group: "Go to", href: base },
      { id: "standard", label: "Group standard", icon: "layers", group: "Go to", href: `${base}/standard` },
      { id: "gaps", label: "Gaps", icon: "gap", group: "Go to", href: `${base}/gaps` },
      { id: "changes", label: "Changes", icon: "changes", group: "Go to", href: `${base}/changes` },
      { id: "members", label: "Members", icon: "users", group: "Go to", href: `${base}/members` },
      ...(isAdmin ? [{ id: "audit", label: "Audit log", icon: "log" as IconName, group: "Go to", href: `${base}/audit` }] : []),
      { id: "settings", label: "Settings", icon: "settings", group: "Go to", href: `${base}/settings` },
    ];
    const orgItems: PaletteItem[] = orgs.map((e) => ({
      id: `org-${e.id}`, label: e.name, hint: "Review mapping", icon: "building", group: "Organisations", href: `${base}/orgs/${e.id}`,
    }));
    const actions: PaletteItem[] = [
      ...(reviewCount ? [{ id: "review", label: `Review queue (${reviewCount})`, icon: "alert" as IconName, group: "Actions", href: `${base}/changes?review=1` }] : []),
      ...(isAdmin ? [{ id: "connect", label: "Connect Xero organisations", icon: "link" as IconName, group: "Actions", run: () => { window.location.href = connectUrl(ws); } }] : []),
    ];
    return [...actions, ...pages, ...orgItems];
  }, [base, orgs, isAdmin, reviewCount, ws]);

  if (loading || !me) return <div className="mx-auto w-full max-w-5xl px-6 py-10"><Loading /></div>;
  if (!membership) return <div className="mx-auto w-full max-w-5xl px-6 py-10"><Loading label="Workspace not found." /></div>;

  async function signOut() {
    await api.logout().catch(() => undefined);
    await refresh();
    router.replace("/");
  }

  const nav: NavItem[] = [
    { href: base, label: "Overview", icon: "home" },
    { href: `${base}/standard`, label: "Group standard", icon: "layers" },
    { href: `${base}/gaps`, label: "Gaps", icon: "gap" },
    { href: `${base}/changes`, label: "Changes", icon: "changes", badge: reviewCount },
  ];
  const manage: NavItem[] = [
    { href: `${base}/members`, label: "Members", icon: "users" },
    { href: `${base}/audit`, label: "Audit log", icon: "log", adminOnly: true },
    { href: `${base}/settings`, label: "Settings", icon: "settings" },
  ];
  const isActive = (href: string) => (href === base ? pathname === base : pathname === href || pathname.startsWith(`${href}/`));

  // Breadcrumb: Workspace / Section [/ Detail]
  const section = [...nav, ...manage].find((n) => n.href !== base && isActive(n.href));
  const org = entity ? orgs.find((e) => e.id === entity) : undefined;
  const crumbs: { label: string; href?: string }[] = [{ label: membership.name, href: base }];
  if (pathname.startsWith(`${base}/orgs/`)) crumbs.push({ label: "Organisations", href: base }, { label: org?.name ?? "Mapping" });
  else if (section) {
    const detail = pathname !== section.href;
    crumbs.push({ label: section.label, href: detail ? section.href : undefined });
    if (detail) crumbs.push({ label: section.label === "Changes" ? "Change" : "Details" });
  } else crumbs.push({ label: "Overview" });

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="px-4 pb-3 pt-4">
        <Link href="/" className="mb-4 flex items-center gap-2.5 px-1">
          <CanopyMark size={28} />
          <span className="text-[17px] font-semibold tracking-tight">Canopy</span>
        </Link>
        <div className="relative">
          <button onClick={() => setSwitcher((s) => !s)} aria-haspopup="listbox" aria-expanded={switcher}
            className="flex w-full items-center gap-3 rounded-xl border border-border bg-surface px-3 py-2.5 text-left shadow-sm transition hover:border-border-strong">
            <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-brand-soft text-brand-strong"><Icon name="building" size={17} /></span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium leading-tight">{membership.name}</span>
              <span className="block text-xs capitalize text-muted">{membership.role}</span>
            </span>
            <Icon name="chevronUpDown" size={16} className="text-subtle" />
          </button>
          {switcher && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setSwitcher(false)} />
              <ul role="listbox" className="absolute left-0 right-0 top-full z-20 mt-1.5 overflow-hidden rounded-xl border border-border bg-surface p-1 shadow-pop animate-pop">
                {me.workspaces.map((w) => (
                  <li key={w.id}>
                    <button onClick={() => { setSwitcher(false); router.push(`/w/${w.id}`); }} role="option" aria-selected={w.id === ws}
                      className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm hover:bg-surface-sunken">
                      <span className="flex-1 truncate">{w.name}</span>
                      {w.id === ws && <Icon name="check" size={15} className="text-brand" />}
                    </button>
                  </li>
                ))}
                <li className="mt-1 border-t border-border pt-1">
                  <Link href="/" onClick={() => setSwitcher(false)} className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-sm text-muted hover:bg-surface-sunken">
                    <Icon name="plus" size={15} /> New or other workspace
                  </Link>
                </li>
              </ul>
            </>
          )}
        </div>
      </div>

      <nav aria-label="Workspace" className="canopy-scroll min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        <NavSection title="Workspace" items={nav} isActive={isActive} isAdmin={isAdmin} />

        <div className="mt-5">
          <div className="mb-1.5 flex items-center justify-between px-3">
            <p className="eyebrow">Organisations</p>
            {isAdmin && (
              <a href={connectUrl(ws)} title="Connect Xero organisations" aria-label="Connect Xero organisations"
                className="rounded-md p-1 text-subtle transition hover:bg-surface-sunken hover:text-brand-strong">
                <Icon name="plus" size={14} />
              </a>
            )}
          </div>
          {orgs.length === 0 ? (
            <p className="px-3 py-1.5 text-[13px] text-subtle">None connected yet.</p>
          ) : (
            <ul className="space-y-0.5">
              {orgs.map((e) => {
                const href = `${base}/orgs/${e.id}`;
                const active = isActive(href);
                return (
                  <li key={e.id}>
                    <Link href={href} aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-[13.5px] transition ${active ? "bg-surface font-medium text-foreground shadow-sm ring-1 ring-border" : "text-muted hover:bg-surface-sunken hover:text-foreground"}`}>
                      <span className={`h-2 w-2 shrink-0 rounded-full ${SYNC_DOT[e.sync_status] ?? SYNC_DOT.never}`} title={e.sync_status} />
                      <span className="truncate">{e.name}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="mt-5">
          <NavSection title="Manage" items={manage} isActive={isActive} isAdmin={isAdmin} />
        </div>
      </nav>

      <div className="border-t border-border p-3">
        <div className="flex items-center gap-3 rounded-xl px-2 py-1.5">
          <Avatar name={me.user.name || me.user.email} size={34} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium leading-tight">{me.user.name || me.user.email.split("@")[0]}</p>
            <p className="truncate text-xs text-muted">{me.user.email}</p>
          </div>
          <button onClick={signOut} title="Sign out" aria-label="Sign out"
            className="rounded-lg p-2 text-muted transition hover:bg-surface-sunken hover:text-foreground">
            <Icon name="logout" size={17} />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[264px] border-r border-border bg-sidebar lg:block">{sidebar}</aside>

      {/* Mobile drawer */}
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden animate-fade-in">
          <div className="absolute inset-0 bg-ink/30 backdrop-blur-[2px]" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 w-[280px] border-r border-border bg-sidebar shadow-pop">{sidebar}</aside>
        </div>
      )}

      <div className="lg:pl-[264px]">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur lg:px-8">
          <button onClick={() => setDrawer(true)} aria-label="Open menu" className="-ml-1 rounded-lg p-2 text-muted hover:bg-surface-sunken lg:hidden">
            <Icon name="menu" size={20} />
          </button>
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-[13px] text-muted">
            {crumbs.map((c, i) => (
              <span key={i} className="flex min-w-0 items-center gap-1.5">
                {i > 0 && <Icon name="chevronRight" size={13} className="shrink-0 text-subtle" />}
                {c.href && i < crumbs.length - 1 ? (
                  <Link href={c.href} className="truncate transition hover:text-foreground">{c.label}</Link>
                ) : (
                  <span className={`truncate ${i === crumbs.length - 1 ? "font-medium text-foreground" : ""}`}>{c.label}</span>
                )}
              </span>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button onClick={() => setPalette(true)}
              className="hidden h-9 w-64 items-center gap-2.5 rounded-[10px] border border-border bg-surface px-3 text-sm text-subtle shadow-sm transition hover:border-border-strong sm:flex">
              <Icon name="search" size={16} />
              <span className="flex-1 text-left">Search or jump to…</span>
              <Kbd>⌘</Kbd><Kbd>K</Kbd>
            </button>
            <button onClick={() => setPalette(true)} aria-label="Search" className="rounded-lg p-2 text-muted hover:bg-surface-sunken sm:hidden">
              <Icon name="search" size={19} />
            </button>
            {reviewCount > 0 && (
              <Link href={`${base}/changes?review=1`} title={`${reviewCount} to review`} aria-label={`${reviewCount} changes to review`}
                className="relative rounded-lg border border-border bg-surface p-2 text-muted shadow-sm transition hover:text-foreground">
                <Icon name="alert" size={17} />
                <span className="tnum absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-amber-500 px-1 text-[10px] font-semibold text-white">{reviewCount}</span>
              </Link>
            )}
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1240px] px-4 py-7 lg:px-8 lg:py-8">{children}</main>
      </div>

      <CommandPalette open={palette} onClose={() => setPalette(false)} items={paletteItems} />
    </div>
  );
}

function NavSection({ title, items, isActive, isAdmin }: {
  title: string; items: NavItem[]; isActive: (href: string) => boolean; isAdmin: boolean;
}) {
  return (
    <div>
      <p className="eyebrow mb-1.5 px-3">{title}</p>
      <ul className="space-y-0.5">
        {items.filter((i) => !i.adminOnly || isAdmin).map((i) => {
          const active = isActive(i.href);
          return (
            <li key={i.href}>
              <Link href={i.href} aria-current={active ? "page" : undefined}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${active ? "bg-surface font-medium text-foreground shadow-sm ring-1 ring-border" : "text-muted hover:bg-surface-sunken hover:text-foreground"}`}>
                <Icon name={i.icon} size={18} className={active ? "text-brand" : ""} />
                <span className="flex-1">{i.label}</span>
                {!!i.badge && <span className="tnum rounded-full bg-amber-100 px-1.5 text-[11px] font-semibold leading-5 text-amber-800">{i.badge}</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
