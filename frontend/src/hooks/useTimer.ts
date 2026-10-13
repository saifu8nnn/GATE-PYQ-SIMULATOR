// Deadline-based timer. Remaining time is always computed from the absolute
// deadline and Date.now(), so background-tab throttling or slow re-renders
// can never make the clock drift.
//
// Robustness notes:
//  * The tick effect depends ONLY on deadlineMs — the onExpire callback is
//    held in a ref, so an inline arrow callback from the caller can never
//    retrigger the effect (which would otherwise loop forever).
//  * setTimer bails out when no field changed, so even a re-render storm
//    cannot create a render loop.

import { useEffect, useRef, useState } from "react";

export interface TimerState {
  remainingMs: number;
  expired: boolean;
  /** true when < 5 minutes remain */
  warning: boolean;
  /** true when < 60 seconds remain */
  critical: boolean;
}

export function remainingFrom(deadlineMs: number | null): number {
  if (deadlineMs === null) return Number.POSITIVE_INFINITY;
  return Math.max(0, deadlineMs - Date.now());
}

function computeState(deadlineMs: number | null): TimerState {
  const remainingMs = remainingFrom(deadlineMs);
  return {
    remainingMs,
    expired: deadlineMs !== null && remainingMs <= 0,
    warning: deadlineMs !== null && remainingMs <= 5 * 60_000,
    critical: deadlineMs !== null && remainingMs <= 60_000,
  };
}

function sameState(a: TimerState, b: TimerState): boolean {
  return (
    a.remainingMs === b.remainingMs &&
    a.expired === b.expired &&
    a.warning === b.warning &&
    a.critical === b.critical
  );
}

export function useTimer(
  deadlineMs: number | null,
  onExpire?: () => void
): TimerState {
  const onExpireRef = useRef(onExpire);
  onExpireRef.current = onExpire;

  const [timer, setTimer] = useState<TimerState>(() => computeState(deadlineMs));

  useEffect(() => {
    // Sync immediately when the deadline changes (including to null).
    setTimer((prev) => {
      const next = computeState(deadlineMs);
      return sameState(prev, next) ? prev : next;
    });

    if (deadlineMs === null) return;

    let fired = false;
    const id = window.setInterval(() => {
      const next = computeState(deadlineMs);
      setTimer((prev) => (sameState(prev, next) ? prev : next));
      if (next.expired && !fired) {
        fired = true;
        onExpireRef.current?.();
      }
    }, 250);
    return () => window.clearInterval(id);
  }, [deadlineMs]);

  return timer;
}

/** Format ms as H:MM:SS (or MM:SS below one hour). */
export function formatMs(ms: number): string {
  if (!Number.isFinite(ms)) return "--:--";
  const totalSec = Math.ceil(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}
