"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, loginUrl } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Button, Card, ErrorNote, Loading } from "@/components/ui";
import { CanopyMark, Icon } from "@/components/icons";

export default function InvitePage() {
  // useSearchParams must sit under a Suspense boundary (Next 16 prerendering).
  return (
    <main className="hero-canopy relative flex min-h-screen flex-1 items-center justify-center px-4 py-16">
      <div className="dot-grid pointer-events-none absolute inset-0 opacity-60" />
      <div className="relative w-full max-w-md animate-rise">
        <div className="mb-6 flex items-center justify-center gap-2.5 text-white">
          <CanopyMark size={32} />
          <span className="text-xl font-semibold tracking-tight">Canopy</span>
        </div>
        <Suspense fallback={<Loading />}>
          <AcceptInvite />
        </Suspense>
      </div>
    </main>
  );
}

function AcceptInvite() {
  const token = useSearchParams().get("token") ?? "";
  const { me, loading, refresh } = useSession();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (loading) return <Loading />;
  if (!token) return <Card padded><ErrorNote message="This invitation link is incomplete." /></Card>;

  if (!me) {
    return (
      <Card padded className="p-7 text-center shadow-pop">
        <span className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-brand-soft text-brand-strong"><Icon name="mail" size={22} /></span>
        <h1 className="text-xl font-semibold tracking-tight">You&apos;ve been invited</h1>
        <p className="mb-6 mt-2 text-sm leading-relaxed text-muted">Sign in with Xero to join this Canopy workspace.</p>
        <a href={loginUrl(`/invite?token=${encodeURIComponent(token)}`)}
          className="flex h-11 w-full items-center justify-center rounded-xl bg-[#13B5EA] text-sm font-semibold text-white shadow-sm transition hover:bg-[#0f9fcf]">
          Sign in with Xero
        </a>
      </Card>
    );
  }

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      const { workspace_id } = await api.acceptInvitation(token);
      await refresh();
      router.replace(`/w/${workspace_id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <Card padded className="p-7 shadow-pop">
      <span className="mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-brand-soft text-brand-strong"><Icon name="mail" size={22} /></span>
      <h1 className="text-xl font-semibold tracking-tight">Join this workspace?</h1>
      <p className="mb-5 mt-2 text-sm leading-relaxed text-muted">
        You&apos;re signed in as <b className="text-foreground">{me.user.email}</b>. The invitation only works for the email address it was sent to.
      </p>
      <ErrorNote message={error} />
      <Button onClick={accept} disabled={busy} className="h-11 w-full">
        {busy ? "Joining…" : "Accept invitation"}
      </Button>
    </Card>
  );
}
