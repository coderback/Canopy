"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { ApiError, api, setCsrfToken, type Me } from "./api";

type SessionState = {
  me: Me | null; // null = signed out
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

const SessionContext = createContext<SessionState | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const apply = useCallback((result: { me: Me } | { error: unknown }) => {
    if ("me" in result) {
      setCsrfToken(result.me.csrf_token);
      setMe(result.me);
      setError(null);
    } else {
      setMe(null);
      // 401 just means signed out; anything else is worth showing.
      const err = result.error;
      setError(err instanceof ApiError && err.status === 401 ? null : (err as Error).message);
    }
    setLoading(false);
  }, []);

  const refresh = useCallback(async () => {
    try {
      apply({ me: await api.me() });
    } catch (error) {
      apply({ error });
    }
  }, [apply]);

  useEffect(() => {
    let cancelled = false;
    api.me().then(
      (me) => !cancelled && apply({ me }),
      (error) => !cancelled && apply({ error }),
    );
    return () => {
      cancelled = true;
    };
  }, [apply]);

  return <SessionContext.Provider value={{ me, loading, error, refresh }}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}

/** The caller's role in a workspace, and whether it can administer. */
export function useRole(workspaceId: string) {
  const { me } = useSession();
  const role = me?.workspaces.find((w) => w.id === workspaceId)?.role ?? null;
  return { role, isAdmin: role === "owner" || role === "admin" };
}
