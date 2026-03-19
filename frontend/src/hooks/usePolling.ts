import { useCallback, useEffect, useRef, useState } from "react";

export interface ResourceState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

export function usePolling<T>(
  loader: () => Promise<T>,
  intervalMs: number,
  deps: ReadonlyArray<unknown> = [],
): ResourceState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loaderRef = useRef(loader);
  const hasLoadedRef = useRef(false);

  loaderRef.current = loader;

  const refresh = useCallback(async () => {
    try {
      const next = await loaderRef.current();
      setData(next);
      setError(null);
      hasLoadedRef.current = true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(!hasLoadedRef.current);
    void refresh();

    const timer = window.setInterval(() => {
      void refresh();
    }, intervalMs);

    return () => {
      window.clearInterval(timer);
    };
  }, [intervalMs, refresh, ...deps]);

  return { data, error, loading, refresh };
}