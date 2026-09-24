"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { api, loginUrl } from "@/lib/api";
import { useSession } from "@/lib/session";
import { Button, Card, ErrorNote, Loading } from "@/components/ui";

export default function InvitePage() {
  // useSearchParams must sit under a Suspense boundary (Next 16 prerendering).
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center px-4 py-16">
      <Suspense fallback={<Loading />}>
        <AcceptInvite />
      </Suspense>
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
  if (!token) return <ErrorNote message="This invitation link is incomplete." />;

  if (!me) {
    return (
      <Card className="p-6 text-center">
        <p className="mb-4 text-sm text-slate-700">You&apos;ve been invited to a Canopy workspace. Sign in with Xero to accept.</p>
        <a href={loginUrl(`/invite?token=${encodeURIComponent(token)}`)} className="inline-flex w-full justify-center rounded-lg bg-[#13B5EA] px-4 py-2.5 text-sm font-semibold text-white">
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
    <Card className="space-y-3 p-6">
      <p className="text-sm text-slate-700">
        Accept this invitation as <b>{me.user.email}</b>? It only works for the email address it was sent to.
      </p>
      <ErrorNote message={error} />
      <Button onClick={accept} disabled={busy} className="w-full">
        {busy ? "Joining…" : "Accept invitation"}
      </Button>
    </Card>
  );
}
