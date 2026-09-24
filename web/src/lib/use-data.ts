"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Load data, expose reload, and optionally poll while `pollWhile(data)` holds
 * (e.g. while an org sync is running). */
export function useData<T>(load: () => Promise<T>, pollWhile?: (data: T) => boolean, intervalMs = 3000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadRef = useRef(load);

  // Keep the latest loader without re-running the initial fetch every render.
  useEffect(() => {
    loadRef.current = load;
  });

  const reload = useCallback(async () => {
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    let cancelled = false; // ignore a response that lands after unmount
    loadRef.current().then(
      (d) => {
        if (!cancelled) {
          setData(d);
          setError(null);
        }
      },
      (err: Error) => {
        if (!cancelled) setError(err.message);
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const polling = data !== null && pollWhile ? pollWhile(data) : false;
  useEffect(() => {
    if (!polling) return;
    const id = setInterval(reload, intervalMs);
    return () => clearInterval(id);
  }, [polling, reload, intervalMs]);

  return { data, error, reload, setError };
}
