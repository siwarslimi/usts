import { useEffect, useRef, useState } from "react";

export type LiveState = "connecting" | "live" | "offline";

/**
 * Subscribes to the backend Server-Sent Events stream. Every event bumps a
 * version number; views refetch when it changes (debounced to absorb bursts).
 */
export function useLiveUpdates(enabled: boolean) {
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<LiveState>("connecting");
  const timer = useRef<number>();

  useEffect(() => {
    if (!enabled) return;
    const es = new EventSource("/api/events");
    const bump = () => {
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setVersion((v) => v + 1), 250);
    };
    es.onopen = () => setState("live");
    es.onerror = () => setState(es.readyState === EventSource.CLOSED ? "offline" : "connecting");
    for (const kind of ["emails", "email", "reply", "sync", "error"]) es.addEventListener(kind, bump);
    return () => {
      es.close();
      window.clearTimeout(timer.current);
    };
  }, [enabled]);

  return { version, state };
}
