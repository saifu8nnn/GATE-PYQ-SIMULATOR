// Exam session state machine. All navigation/response/marking rules from
// PHASE 7.4–7.5 live here so components stay declarative:
//   * Save & Next           → retains response, advances
//   * Mark for Review & Next→ marks AND retains response, advances
//   * Clear Response        → clears only the current question's response
//   * Palette click         → opens that question without losing responses
// The whole session persists after every mutation (refresh-safe).

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  DisplayQuestion,
  PaletteState,
  ResponseValue,
  SessionConfig,
} from "../types";
import {
  PersistedSession,
  clearActiveSession,
  saveActiveSession,
} from "../services/storage";

export interface SessionState {
  questionIds: string[];
  currentIdx: number;
  responses: Record<string, ResponseValue>;
  savedIds: Set<string>;
  markedIds: Set<string>;
  visitedIds: Set<string>;
  startedAt: number;
  deadlineMs: number | null;
}

function shuffle<T>(arr: T[], seed: number): T[] {
  // Deterministic-ish Fisher-Yates using provided seed so a restored shuffled
  // session keeps its order (the order itself is persisted anyway).
  const out = [...arr];
  let s = seed;
  for (let i = out.length - 1; i > 0; i--) {
    s = (s * 1664525 + 1013904223) % 4294967296;
    const j = s % (i + 1);
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

export function startSession(
  questions: DisplayQuestion[],
  config: SessionConfig
): PersistedSession {
  let pool = [...questions];
  if (config.shuffled) pool = shuffle(pool, Date.now() % 2 ** 31);
  if (config.questionCount !== null && config.questionCount < pool.length) {
    pool = pool.slice(0, config.questionCount);
  }
  const now = Date.now();
  return {
    questionIds: pool.map((q) => q.id),
    currentIdx: 0,
    responses: {},
    savedIds: [],
    markedIds: [],
    visitedIds: pool.length > 0 ? [pool[0].id] : [],
    startedAt: new Date(now).toISOString(),
    deadlineMs:
      config.timed && config.durationSec !== null ? now + config.durationSec * 1000 : null,
    mode: config.mode,
    filterLabel: config.filterLabel,
    timed: config.timed,
    durationSec: config.durationSec,
    shuffled: config.shuffled,
  };
}

function persist(s: SessionState): void {
  const p: PersistedSession = {
    questionIds: s.questionIds,
    currentIdx: s.currentIdx,
    responses: s.responses,
    savedIds: [...s.savedIds],
    markedIds: [...s.markedIds],
    visitedIds: [...s.visitedIds],
    startedAt: new Date(s.startedAt).toISOString(),
    deadlineMs: s.deadlineMs,
    mode: "",
    filterLabel: "",
    timed: s.deadlineMs !== null,
    durationSec: null,
    shuffled: false,
  };
  saveActiveSession(p);
}

function fromPersisted(p: PersistedSession): SessionState {
  return {
    questionIds: p.questionIds,
    currentIdx: Math.min(Math.max(0, p.currentIdx), Math.max(0, p.questionIds.length - 1)),
    responses: p.responses ?? {},
    savedIds: new Set(p.savedIds ?? []),
    markedIds: new Set(p.markedIds ?? []),
    visitedIds: new Set(p.visitedIds ?? []),
    startedAt: new Date(p.startedAt).getTime() || Date.now(),
    deadlineMs: p.deadlineMs ?? null,
  };
}

export function useSession(
  questionsById: Map<string, DisplayQuestion>,
  initial: PersistedSession | null
) {
  const [state, setState] = useState<SessionState>(() =>
    initial ? fromPersisted(initial) : null as unknown as SessionState
  );
  const [submitted, setSubmitted] = useState(false);
  const skipPersist = useRef(true);

  useEffect(() => {
    if (skipPersist.current) {
      skipPersist.current = false;
      return;
    }
    if (!submitted) persist(state);
  }, [state, submitted]);

  const currentId: string | null = state.questionIds[state.currentIdx] ?? null;
  const currentQuestion: DisplayQuestion | null =
    currentId !== null ? questionsById.get(currentId) ?? null : null;

  /** Set/replace the current question's draft response (kept on navigation). */
  const setResponse = useCallback(
    (value: ResponseValue) => {
      if (currentId === null) return;
      setState((s) => ({ ...s, responses: { ...s.responses, [currentId]: value } }));
    },
    [currentId]
  );

  const goTo = useCallback((idx: number) => {
    setState((s) => {
      if (idx < 0 || idx >= s.questionIds.length) return s;
      const visited = new Set(s.visitedIds);
      visited.add(s.questionIds[idx]);
      return { ...s, currentIdx: idx, visitedIds: visited };
    });
  }, []);

  /** Commit the current response and advance. */
  const saveAndNext = useCallback(() => {
    if (currentId === null) return;
    setState((s) => {
      const saved = new Set(s.savedIds);
      saved.add(currentId);
      const visited = new Set(s.visitedIds);
      const nextIdx = Math.min(s.currentIdx + 1, s.questionIds.length - 1);
      visited.add(s.questionIds[nextIdx]);
      return { ...s, savedIds: saved, currentIdx: nextIdx, visitedIds: visited };
    });
  }, [currentId]);

  /** Mark for review WITHOUT deleting the response, then advance. */
  const markAndNext = useCallback(() => {
    if (currentId === null) return;
    setState((s) => {
      const marked = new Set(s.markedIds);
      marked.add(currentId);
      const saved = new Set(s.savedIds);
      saved.add(currentId); // response (if any) is retained and committed
      const nextIdx = Math.min(s.currentIdx + 1, s.questionIds.length - 1);
      const visited = new Set(s.visitedIds);
      visited.add(s.questionIds[nextIdx]);
      return { ...s, markedIds: marked, savedIds: saved, currentIdx: nextIdx, visitedIds: visited };
    });
  }, [currentId]);

  const unmark = useCallback(() => {
    if (currentId === null) return;
    setState((s) => {
      const marked = new Set(s.markedIds);
      marked.delete(currentId);
      return { ...s, markedIds: marked };
    });
  }, [currentId]);

  /** Clear ONLY the current question's response. */
  const clearResponse = useCallback(() => {
    if (currentId === null) return;
    setState((s) => {
      const responses = { ...s.responses };
      delete responses[currentId];
      const saved = new Set(s.savedIds);
      saved.delete(currentId);
      return { ...s, responses, savedIds: saved };
    });
  }, [currentId]);

  /** GATE-style palette state with response+mark combinations. */
  const paletteState = useCallback(
    (qid: string): PaletteState => {
      const hasResponse =
        state.responses[qid] !== undefined &&
        state.responses[qid] !== null &&
        !(Array.isArray(state.responses[qid]) && state.responses[qid]!.length === 0) &&
        state.responses[qid] !== "";
      const marked = state.markedIds.has(qid);
      const visited = state.visitedIds.has(qid);
      if (marked) return hasResponse ? "answered_marked" : "marked";
      if (hasResponse) return "answered";
      if (visited) return "not_answered";
      return "not_visited";
    },
    [state]
  );

  /** End the session: persist nothing more and clear the active-session slot. */
  const finalize = useCallback(() => {
    setSubmitted(true);
    clearActiveSession();
  }, []);

  const counts = useMemo(() => {
    let answered = 0;
    let marked = 0;
    for (const qid of state.questionIds) {
      const st = paletteState(qid);
      if (st === "answered" || st === "answered_marked") answered++;
      if (st === "marked" || st === "answered_marked") marked++;
    }
    return { answered, unanswered: state.questionIds.length - answered, marked };
  }, [state.questionIds, paletteState]);

  return {
    state,
    submitted,
    currentId,
    currentQuestion,
    setResponse,
    goTo,
    saveAndNext,
    markAndNext,
    unmark,
    clearResponse,
    paletteState,
    finalize,
    counts,
  };
}
