"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Loading } from "@/components/ui";

const TABS = [
  { href: "", label: "Overview" },
  { href: "/standard", label: "Group standard" },
  { href: "/gaps", label: "Gaps" },
  { href: "/members", label: "Members" },
  { href: "/audit", label: "Audit log", adminOnly: true },
];

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { ws } = useParams<{ ws: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const { me, loading, refresh } = useSession();
  const membership = me?.workspaces.find((w) => w.id === ws);
  const isAdmin = membership?.role === "owner" || membership?.role === "admin";

  useEffect(() => {
    if (!loading && !me) router.replace("/");
  }, [loading, me, router]);

  if (loading || !me) return <Loading />;
  if (!membership) return <Loading label="Workspace not found." />;

  const base = `/w/${ws}`;
  async function signOut() {
    await api.logout().catch(() => undefined);
    await refresh();
    router.replace("/");
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-20 border-b border-border bg-surface/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3 lg:px-6">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-xl">🌳</span>
            <span className="font-semibold text-slate-900">Canopy</span>
          </Link>
          <span className="text-sm text-muted">{membership.name}</span>
          <nav className="flex flex-wrap gap-1 text-sm" aria-label="Workspace">
            {TABS.filter((t) => !t.adminOnly || isAdmin).map((t) => {
              const href = `${base}${t.href}`;
              const active = t.href === "" ? pathname === base || pathname.startsWith(`${base}/orgs`) : pathname.startsWith(href);
              return (
                <Link key={t.href} href={href} aria-current={active ? "page" : undefined}
                  className={`rounded-md px-3 py-1.5 ${active ? "bg-emerald-50 font-medium text-brand-strong" : "text-slate-600 hover:bg-slate-100"}`}>
                  {t.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="text-muted">{me.user.email}</span>
            <button onClick={signOut} className="text-slate-600 hover:text-slate-900">Sign out</button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-6">{children}</main>
    </div>
  );
}
