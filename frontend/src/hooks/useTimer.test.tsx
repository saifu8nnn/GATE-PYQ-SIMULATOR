// Timer behavior (acceptance item 10): drift-free countdown derived from an
// absolute deadline, plus formatting.

import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { formatMs, remainingFrom, useTimer } from "./useTimer";

describe("formatMs", () => {
  it("formats minutes and seconds", () => {
    expect(formatMs(65_000)).toBe("1:05");
    expect(formatMs(59_000)).toBe("0:59");
    expect(formatMs(59_500)).toBe("1:00"); // rounds up to whole seconds
    expect(formatMs(3_600_000 + 60_000)).toBe("1:01:00");
    expect(formatMs(Number.POSITIVE_INFINITY)).toBe("--:--");
  });
});

describe("remainingFrom", () => {
  it("computes remaining time from the absolute deadline (no drift source)", () => {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(new Date("2026-01-01T10:00:00Z"));
      const deadline = Date.now() + 120_000;
      expect(remainingFrom(deadline)).toBe(120_000);
      vi.setSystemTime(new Date("2026-01-01T10:01:00Z")); // one minute later
      expect(remainingFrom(deadline)).toBe(60_000);
      expect(remainingFrom(null)).toBe(Number.POSITIVE_INFINITY);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("useTimer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("counts down and fires onExpire exactly once at the deadline", () => {
    const onExpire = vi.fn();
    const deadline = Date.now() + 1000;
    const { result } = renderHook(() => useTimer(deadline, onExpire));

    expect(result.current.remainingMs).toBe(1000);
    expect(result.current.expired).toBe(false);

    act(() => vi.advanceTimersByTime(750)); // three 250ms ticks
    expect(result.current.remainingMs).toBe(250);

    act(() => vi.advanceTimersByTime(500)); // past deadline
    expect(result.current.expired).toBe(true);
    expect(onExpire).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(1000)); // must not fire again
    expect(onExpire).toHaveBeenCalledTimes(1);
  });

  it("flags warning (≤5 min) and critical (≤1 min) thresholds", () => {
    const deadline = Date.now() + 4 * 60_000; // 4 minutes
    const { result } = renderHook(() => useTimer(deadline));
    expect(result.current.warning).toBe(true);
    expect(result.current.critical).toBe(false);

    act(() => vi.advanceTimersByTime(3 * 60_000 + 30_000)); // 30s left
    expect(result.current.critical).toBe(true);
  });

  it("is inert without a deadline (untimed sessions)", () => {
    const onExpire = vi.fn();
    const { result } = renderHook(() => useTimer(null, onExpire));
    act(() => vi.advanceTimersByTime(600_000));
    expect(result.current.expired).toBe(false);
    expect(onExpire).not.toHaveBeenCalled();
  });
});
