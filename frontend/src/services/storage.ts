// Local persistence (localStorage). Question data and user data are strictly
// separate: syncing a new dataset never touches these stores, and records
// referencing missing question IDs are tolerated (never crash) and can be
// pruned explicitly.

import { ProgressEntry, ResponseValue, SessionSummary } from "../types";

const KEYS = {
  bookmarks: "gatepyq.bookmarks.v1",
  progress: "gatepyq.progress.v1",
  sessions: "gatepyq.sessions.v1",
  activeSession: "gatepyq.activeSession.v1",
} as const;

// ── low-level helpers ────────────────────────────────────────────────────────

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage full / private mode — persistence is best-effort, never fatal
  }
}

/** Test/story helper: wipe every persisted store (used by reset + tests). */
export function resetAllStorage(): void {
  Object.values(KEYS).forEach((k) => localStorage.removeItem(k));
}

// ── bookmarks ────────────────────────────────────────────────────────────────

export function getBookmarks(): string[] {
  const list = read<string[]>(KEYS.bookmarks, []);
  return Array.isArray(list) ? list.filter((x) => typeof x === "string") : [];
}

export function isBookmarked(qid: string): boolean {
  return getBookmarks().includes(qid);
}

/** Toggle a bookmark; returns the new bookmarked state. */
export function toggleBookmark(qid: string): boolean {
  const set = new Set(getBookmarks());
  let added: boolean;
  if (set.has(qid)) {
    set.delete(qid);
    added = false;
  } else {
    set.add(qid);
    added = true;
  }
  write(KEYS.bookmarks, [...set]);
  return added;
}

// ── per-question attempt progress ────────────────────────────────────────────

export function getProgress(): ProgressEntry[] {
  const list = read<ProgressEntry[]>(KEYS.progress, []);
  return Array.isArray(list) ? list : [];
}

/** Record graded attempts from a submitted session (latest attempt wins). */
export function recordProgress(entries: ProgressEntry[]): void {
  const byId = new Map<string, ProgressEntry>();
  for (const e of getProgress()) byId.set(e.qid, e);
  for (const e of entries) byId.set(e.qid, e); // newest attempt replaces older
  write(KEYS.progress, [...byId.values()]);
}

/** Remove progress entries whose question no longer exists in the dataset. */
export function pruneProgress(validIds: Set<string>): number {
  const before = getProgress();
  const after = before.filter((e) => validIds.has(e.qid));
  const removed = before.length - after.length;
  if (removed > 0) write(KEYS.progress, after);
  return removed;
}

// ── session history ──────────────────────────────────────────────────────────

export function getSessions(): SessionSummary[] {
  const list = read<SessionSummary[]>(KEYS.sessions, []);
  return Array.isArray(list) ? list : [];
}

export function recordSession(summary: SessionSummary): void {
  const list = getSessions();
  list.push(summary);
  // keep the most recent 200 sessions
  write(KEYS.sessions, list.slice(-200));
}

export function clearSessionHistory(): void {
  write(KEYS.sessions, []);
}

// ── active (in-progress) session ─────────────────────────────────────────────

export interface PersistedSession {
  questionIds: string[];
  currentIdx: number;
  responses: Record<string, ResponseValue>;
  savedIds: string[]; // questions whose response was committed via Save
  markedIds: string[];
  visitedIds: string[];
  startedAt: string;
  deadlineMs: number | null; // absolute epoch ms for timed sessions
  mode: string;
  filterLabel: string;
  timed: boolean;
  durationSec: number | null;
  shuffled: boolean;
}

export function saveActiveSession(s: PersistedSession): void {
  write(KEYS.activeSession, s);
}

export function loadActiveSession(): PersistedSession | null {
  const s = read<PersistedSession | null>(KEYS.activeSession, null);
  if (!s || !Array.isArray(s.questionIds) || s.questionIds.length === 0) return null;
  return s;
}

export function clearActiveSession(): void {
  localStorage.removeItem(KEYS.activeSession);
}

// ── explicit user reset ──────────────────────────────────────────────────────

/** Full progress reset. Only ever called from an explicit confirmed action. */
export function resetProgress(): void {
  write(KEYS.progress, []);
  write(KEYS.sessions, []);
  localStorage.removeItem(KEYS.activeSession);
  // bookmarks are intentionally kept: reset "practice progress", not preferences
}
