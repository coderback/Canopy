"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, loginUrl } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Button, ErrorNote, Input, Loading } from "@/components/ui";
import { CanopyMark, Icon, type IconName } from "@/components/icons";

export default function Home() {
  const { me, loading, error } = useSession();
  const router = useRouter();

  // Signed in with exactly one workspace: go straight there.
  useEffect(() => {
    if (me && me.workspaces.length === 1) router.replace(`/w/${me.workspaces[0].id}`);
  }, [me, router]);

  if (loading) return <div className="mx-auto w-full max-w-3xl px-6 py-16"><Loading /></div>;

  return (
    <div className="grid min-h-screen flex-1 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <Hero />
      <main className="flex flex-col justify-center px-6 py-12 sm:px-12">
        <div className="mx-auto w-full max-w-sm animate-rise">
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <CanopyMark size={30} />
            <span className="text-lg font-semibold tracking-tight">Canopy</span>
          </div>
          <ErrorNote message={error} />
          {!me ? <SignIn /> : me.workspaces.length === 0 ? <CreateWorkspace /> : <ChooseWorkspace />}
        </div>
      </main>
    </div>
  );
}

function Hero() {
  const points: { icon: IconName; title: string; body: string }[] = [
    { icon: "lock", title: "Read-only by default", body: "Canopy can see your charts of accounts but can't change a thing in Xero until you say so." },
    { icon: "sparkle", title: "AI suggests, you decide", body: "Exact matches are instant. An AI proposes the rest. Nothing is final until a person confirms it." },
    { icon: "shield", title: "Built for finance teams", body: "Two-person approval, a full audit trail, and tenant isolation enforced in the database." },
  ];
  return (
    <aside className="hero-canopy relative hidden overflow-hidden text-white lg:flex lg:flex-col lg:justify-between lg:p-12">
      <div className="dot-grid pointer-events-none absolute inset-0 opacity-70" />
      <div className="relative flex items-center gap-2.5">
        <CanopyMark size={34} />
        <span className="text-xl font-semibold tracking-tight">Canopy</span>
      </div>

      <div className="relative max-w-xl">
        <h1 className="text-[44px] font-semibold leading-[1.08] tracking-tight">
          One chart of accounts.<br />
          <span className="text-emerald-300">Every Xero organisation.</span>
        </h1>
        <p className="mt-5 max-w-md text-[17px] leading-relaxed text-emerald-50/80">
          Map each entity in your group to a single standard, see exactly what&apos;s missing, and keep it all consistent, without forcing every org to be identical.
        </p>

        <MappingArt />

        <ul className="mt-10 space-y-5">
          {points.map((p) => (
            <li key={p.title} className="flex gap-4">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/10 text-emerald-200 ring-1 ring-inset ring-white/15">
                <Icon name={p.icon} size={18} />
              </span>
              <div>
                <p className="font-medium">{p.title}</p>
                <p className="mt-0.5 text-sm leading-relaxed text-emerald-50/70">{p.body}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <p className="relative text-xs text-emerald-100/50">Built from research with a multi-entity group&apos;s finance team.</p>
    </aside>
  );
}

/** A tiny, decorative picture of what Canopy does: several org accounts converge on one group account. */
function MappingArt() {
  const rows = [
    { org: "Acme Leisure UK", code: "200", name: "Sales" },
    { org: "Acme Hotels", code: "4000", name: "Revenue – Sales" },
    { org: "Acme Acquired Ltd", code: "SAL", name: "Sales income" },
  ];
  return (
    <div className="mt-9 grid max-w-lg grid-cols-[1fr_auto_auto] items-center gap-x-3 gap-y-2 rounded-2xl border border-white/15 bg-white/[0.07] p-4 backdrop-blur-sm" aria-hidden="true">
      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r.org} className="flex items-center gap-2.5 rounded-lg bg-white/10 px-3 py-2">
            <span className="font-mono text-xs text-emerald-200">{r.code}</span>
            <span className="truncate text-[13px]">{r.name}</span>
            <span className="ml-auto hidden truncate text-[11px] text-emerald-100/50 sm:block">{r.org}</span>
          </div>
        ))}
      </div>
      <div className="flex flex-col items-center gap-1 text-emerald-300">
        <Icon name="merge" size={22} />
        <span className="text-[10px] uppercase tracking-wider">maps to</span>
      </div>
      <div className="rounded-xl bg-emerald-300 px-4 py-3 text-emerald-950 shadow-lg">
        <span className="block font-mono text-[11px] opacity-70">GROUP</span>
        <span className="block text-sm font-semibold">200 Sales</span>
      </div>
    </div>
  );
}

function SignIn() {
  return (
    <>
      <h2 className="text-[28px] font-semibold tracking-tight">Welcome to Canopy</h2>
      <p className="mt-2 text-sm leading-relaxed text-muted">Sign in with the Xero account you use for your group&apos;s organisations.</p>
      <a href={loginUrl("/")}
        className="mt-7 flex h-11 w-full items-center justify-center gap-2.5 rounded-xl bg-[#13B5EA] text-sm font-semibold text-white shadow-sm transition hover:bg-[#0f9fcf]">
        <span className="grid h-5 w-5 place-items-center rounded-full bg-white text-[11px] font-bold text-[#13B5EA]">x</span>
        Sign in with Xero
      </a>
      <div className="mt-6 flex gap-3 rounded-xl border border-border bg-surface p-3.5 text-[13px] leading-relaxed text-muted">
        <Icon name="shield" size={18} className="mt-0.5 text-brand" />
        <p>Signing in shares only your name and email. Connecting organisations is a separate, read-only step you control.</p>
      </div>
    </>
  );
}

function CreateWorkspace() {
  const { refresh } = useSession();
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const { id } = await api.createWorkspace(name);
      await refresh();
      router.push(`/w/${id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <>
      <h2 className="text-[28px] font-semibold tracking-tight">Name your group</h2>
      <p className="mt-2 text-sm leading-relaxed text-muted">A workspace holds every Xero organisation in your group, plus the standard they&apos;re mapped to.</p>
      <form onSubmit={create} className="mt-7 space-y-4">
        <div>
          <label className="mb-1.5 block text-sm font-medium" htmlFor="ws-name">Group name</label>
          <Input id="ws-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Acme Leisure Group" required autoFocus />
        </div>
        <ErrorNote message={error} />
        <Button type="submit" disabled={busy || !name.trim()} className="h-11 w-full">
          {busy ? "Creating…" : "Create workspace"}
        </Button>
      </form>
    </>
  );
}

function ChooseWorkspace() {
  const { me } = useSession();
  const router = useRouter();
  return (
    <>
      <h2 className="text-[28px] font-semibold tracking-tight">Choose a workspace</h2>
      <p className="mt-2 text-sm text-muted">Signed in as {me!.user.email}.</p>
      <ul className="mt-6 space-y-2.5">
        {me!.workspaces.map((w) => (
          <li key={w.id}>
            <button onClick={() => router.push(`/w/${w.id}`)}
              className="group flex w-full items-center gap-3.5 rounded-2xl border border-border bg-surface p-3.5 text-left shadow-card transition hover:border-brand/50 hover:shadow-md">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-brand-soft text-brand-strong"><Icon name="building" size={19} /></span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{w.name}</span>
                <span className="block text-xs capitalize text-muted">{w.role}</span>
              </span>
              <Icon name="arrowRight" size={17} className="text-subtle transition group-hover:translate-x-0.5 group-hover:text-brand" />
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
