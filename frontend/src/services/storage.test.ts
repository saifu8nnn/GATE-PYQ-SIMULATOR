// Persistence tests: bookmarks, progress and session history survive a
// "reload" (state re-read from storage), and reset is explicit (items 15–16).

import { describe, expect, it } from "vitest";
import {
  clearSessionHistory,
  getBookmarks,
  getProgress,
  getSessions,
  isBookmarked,
  loadActiveSession,
  pruneProgress,
  recordProgress,
  recordSession,
  resetProgress,
  saveActiveSession,
  toggleBookmark,
} from "./storage";
import { SessionSummary } from "../types";

function summary(id: string): SessionSummary {
  return {
    id,
    startedAt: new Date().toISOString(),
    submittedAt: new Date().toISOString(),
    mode: "subject",
    filterLabel: "Databases",
    totalQuestions: 10,
    attempted: 8,
    correct: 5,
    incorrect: 3,
    ungradable: 2,
    marksAwarded: 10,
    marksAvailable: 16,
    timeUsedSec: 600,
    timed: false,
  };
}

describe("bookmarks", () => {
  it("toggles and persists across re-reads", () => {
    expect(toggleBookmark("q1")).toBe(true);
    expect(isBookmarked("q1")).toBe(true);
    // simulate reload: state comes from storage, not memory
    expect(getBookmarks()).toEqual(["q1"]);
    expect(toggleBookmark("q1")).toBe(false);
    expect(isBookmarked("q1")).toBe(false);
  });
});

describe("progress", () => {
  it("keeps the latest attempt per question", () => {
    recordProgress([{ qid: "q1", status: "incorrect", at: "t1", sessionId: "s1" }]);
    recordProgress([{ qid: "q1", status: "correct", at: "t2", sessionId: "s2" }]);
    const p = getProgress();
    expect(p).toHaveLength(1);
    expect(p[0].status).toBe("correct");
  });

  it("prunes attempts whose questions vanished from the dataset", () => {
    recordProgress([
      { qid: "keep", status: "correct", at: "t", sessionId: "s" },
      { qid: "gone", status: "incorrect", at: "t", sessionId: "s" },
    ]);
    const removed = pruneProgress(new Set(["keep"]));
    expect(removed).toBe(1);
    expect(getProgress().map((e) => e.qid)).toEqual(["keep"]);
  });
});

describe("session history", () => {
  it("records sessions across reloads and supports explicit clearing", () => {
    recordSession(summary("s1"));
    recordSession(summary("s2"));
    expect(getSessions().map((s) => s.id)).toEqual(["s1", "s2"]);
    clearSessionHistory();
    expect(getSessions()).toEqual([]);
  });
});

describe("active session + reset", () => {
  it("round-trips an active session", () => {
    saveActiveSession({
      questionIds: ["a", "b"],
      currentIdx: 1,
      responses: { a: "A" },
      savedIds: ["a"],
      markedIds: [],
      visitedIds: ["a", "b"],
      startedAt: new Date().toISOString(),
      deadlineMs: null,
      mode: "topic",
      filterLabel: "B Tree",
      timed: false,
      durationSec: null,
      shuffled: false,
    });
    const loaded = loadActiveSession();
    expect(loaded?.questionIds).toEqual(["a", "b"]);
    expect(loaded?.responses).toEqual({ a: "A" });
  });

  it("resetProgress clears progress/sessions/active but keeps bookmarks", () => {
    toggleBookmark("keep-me");
    recordSession(summary("sx"));
    recordProgress([{ qid: "qx", status: "correct", at: "t", sessionId: "sx" }]);
    saveActiveSession({
      questionIds: ["q"],
      currentIdx: 0,
      responses: {},
      savedIds: [],
      markedIds: [],
      visitedIds: ["q"],
      startedAt: new Date().toISOString(),
      deadlineMs: null,
      mode: "mixed",
      filterLabel: "",
      timed: false,
      durationSec: null,
      shuffled: false,
    });

    resetProgress();

    expect(getSessions()).toEqual([]);
    expect(getProgress()).toEqual([]);
    expect(loadActiveSession()).toBeNull();
    expect(isBookmarked("keep-me")).toBe(true); // bookmarks survive
  });
});

describe("corrupt storage", () => {
  it("never throws on garbage JSON", () => {
    localStorage.setItem("gatepyq.bookmarks.v1", "{not json");
    expect(getBookmarks()).toEqual([]);
  });
});
