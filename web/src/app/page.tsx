"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, loginUrl } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Button, Card, ErrorNote, Loading } from "@/components/ui";

export default function Home() {
  const { me, loading, error } = useSession();
  const router = useRouter();

  // Signed in with exactly one workspace: go straight there.
  useEffect(() => {
    if (me && me.workspaces.length === 1) router.replace(`/w/${me.workspaces[0].id}`);
  }, [me, router]);

  if (loading) return <Loading />;

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-16">
      <div className="mb-6 text-center">
        <div className="text-3xl">🌳</div>
        <h1 className="mt-2 text-xl font-semibold text-slate-900">Canopy</h1>
        <p className="mt-1 text-sm text-muted">One group chart of accounts across every Xero organisation.</p>
      </div>
      <ErrorNote message={error} />
      {!me ? <SignIn /> : me.workspaces.length === 0 ? <CreateWorkspace /> : <ChooseWorkspace />}
    </main>
  );
}

function SignIn() {
  return (
    <Card className="p-6 text-center">
      <p className="mb-4 text-sm text-slate-700">Sign in with the Xero account you use for your group&apos;s organisations.</p>
      <a href={loginUrl("/")} className="inline-flex w-full items-center justify-center rounded-lg bg-[#13B5EA] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#0f9fcf]">
        Sign in with Xero
      </a>
      <p className="mt-3 text-xs text-muted">Signing in shares only your name and email. Connecting organisations is a separate, read-only step.</p>
    </Card>
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
    <Card className="p-6">
      <form onSubmit={create} className="space-y-3">
        <label className="block text-sm font-medium text-slate-800" htmlFor="ws-name">
          Name your group
        </label>
        <input
          id="ws-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Acme Leisure Group"
          className="w-full rounded-lg border border-border-strong px-3 py-2 text-sm"
          required
        />
        <ErrorNote message={error} />
        <Button type="submit" disabled={busy || !name.trim()} className="w-full">
          {busy ? "Creating…" : "Create workspace"}
        </Button>
      </form>
    </Card>
  );
}

function ChooseWorkspace() {
  const { me } = useSession();
  const router = useRouter();
  return (
    <Card className="divide-y divide-border">
      {me!.workspaces.map((w) => (
        <button key={w.id} onClick={() => router.push(`/w/${w.id}`)} className="flex w-full items-center justify-between px-4 py-3 text-left text-sm hover:bg-surface-sunken">
          <span className="font-medium text-slate-900">{w.name}</span>
          <span className="text-muted">{w.role}</span>
        </button>
      ))}
    </Card>
  );
}
