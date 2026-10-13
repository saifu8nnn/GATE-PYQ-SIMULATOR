// Session state machine tests (acceptance items 3–9): responses survive
// navigation, marking never deletes, clearing is targeted, palette states
// follow the documented transitions, and the session persists.

import { describe, expect, it } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useSession, startSession } from "./useSession";
import { DisplayQuestion, SessionConfig } from "../types";
import { loadActiveSession } from "../services/storage";

function q(id: string, type: DisplayQuestion["questionType"] = "MCQ"): DisplayQuestion {
  return {
    id,
    exam: "GATE CSE",
    year: 2000,
    set: null,
    subject: "Databases",
    topic: "B Tree",
    subtopic: null,
    questionNumber: "1",
    questionType: type,
    marks: 1,
    optionsPresent: type === "MCQ" || type === "MSQ",
    optionLabels: type === "MCQ" || type === "MSQ" ? ["A", "B", "C", "D"] : [],
    imageUrl: `/images/${id}.png`,
    sourcePages: [1],
    verified: false,
  };
}

const questions = [q("q1", "MCQ"), q("q2", "MSQ"), q("q3", "NAT")];
const byId = new Map(questions.map((x) => [x.id, x]));

const config: SessionConfig = {
  mode: "subject",
  filterLabel: "Databases",
  timed: false,
  durationSec: null,
  shuffled: false,
  questionCount: null,
};

function setup() {
  const persisted = startSession(questions, config);
  const hook = renderHook(() => useSession(byId, persisted));
  return hook;
}

describe("navigation + response retention", () => {
  it("MCQ response survives navigating away and back", () => {
    const { result } = setup();
    act(() => result.current.setResponse("B"));
    act(() => result.current.saveAndNext()); // to q2
    act(() => result.current.goTo(0)); // back to q1
    expect(result.current.state.responses["q1"]).toBe("B");
  });

  it("NAT input is preserved on navigation", () => {
    const { result } = setup();
    act(() => result.current.goTo(2));
    act(() => result.current.setResponse("42.5"));
    act(() => result.current.goTo(0));
    act(() => result.current.goTo(2));
    expect(result.current.state.responses["q3"]).toBe("42.5");
  });

  it("MSQ permits multiple selections", () => {
    const { result } = setup();
    act(() => result.current.goTo(1));
    act(() => result.current.setResponse(["A", "C"]));
    expect(result.current.state.responses["q2"]).toEqual(["A", "C"]);
  });

  it("Save & Next advances exactly one question", () => {
    const { result } = setup();
    act(() => result.current.setResponse("A"));
    act(() => result.current.saveAndNext());
    expect(result.current.state.currentIdx).toBe(1);
    expect(result.current.state.savedIds.has("q1")).toBe(true);
  });
});

describe("mark for review", () => {
  it("retains the response when marking and advancing", () => {
    const { result } = setup();
    act(() => result.current.setResponse("D"));
    act(() => result.current.markAndNext());
    expect(result.current.state.responses["q1"]).toBe("D"); // NOT deleted
    expect(result.current.state.markedIds.has("q1")).toBe(true);
    expect(result.current.state.currentIdx).toBe(1);
    expect(result.current.paletteState("q1")).toBe("answered_marked");
  });

  it("can mark an unanswered question and later unmark it", () => {
    const { result } = setup();
    act(() => result.current.markAndNext()); // mark q1 without response
    expect(result.current.paletteState("q1")).toBe("marked");
    act(() => result.current.goTo(0));
    act(() => result.current.unmark());
    expect(result.current.paletteState("q1")).toBe("not_answered");
  });
});

describe("clear response", () => {
  it("clears only the current question's response", () => {
    const { result } = setup();
    act(() => result.current.setResponse("B"));
    act(() => result.current.saveAndNext());
    act(() => result.current.setResponse(["A"]));
    act(() => result.current.clearResponse()); // clears q2 only
    expect(result.current.state.responses["q2"]).toBeUndefined();
    expect(result.current.state.responses["q1"]).toBe("B");
  });
});

describe("palette states", () => {
  it("walks through all five states correctly", () => {
    const { result } = setup();
    // q1 is the current question at session start → already "visited"
    expect(result.current.paletteState("q1")).toBe("not_answered");
    act(() => result.current.setResponse("A"));
    expect(result.current.paletteState("q1")).toBe("answered");
    // q2: visited, unanswered
    act(() => result.current.saveAndNext());
    expect(result.current.paletteState("q2")).toBe("not_answered");
    // q3: not visited yet
    expect(result.current.paletteState("q3")).toBe("not_visited");
    // answered + marked (advance to q3 first, then answer and mark it)
    act(() => result.current.goTo(2));
    act(() => result.current.setResponse("7"));
    act(() => result.current.markAndNext()); // stays on last question
    expect(result.current.paletteState("q3")).toBe("answered_marked");
  });
});

describe("persistence + counts", () => {
  it("persists the session after every mutation (refresh-safe)", () => {
    const { result } = setup();
    act(() => result.current.setResponse("B"));
    act(() => result.current.saveAndNext());
    const stored = loadActiveSession();
    expect(stored?.responses["q1"]).toBe("B");
    expect(stored?.currentIdx).toBe(1);
  });

  it("computes answered/unanswered/marked counts", () => {
    const { result } = setup();
    act(() => result.current.setResponse("A"));
    act(() => result.current.saveAndNext());
    act(() => result.current.markAndNext()); // marks q2 (unanswered)
    expect(result.current.counts.answered).toBe(1);
    expect(result.current.counts.marked).toBe(1);
    expect(result.current.counts.unanswered).toBe(2);
  });
});
