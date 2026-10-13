// Unit tests for the grading service — the scoring rules are the most
// safety-critical part of the app (PHASE 7.7, acceptance items 11–14).

import { describe, expect, it } from "vitest";
import { gradeResponse } from "./grading";
import { DisplayQuestion, GradingEntry, QuestionType } from "../types";

function q(type: QuestionType, labels: string[] = []): DisplayQuestion {
  return {
    id: "test-q",
    exam: "GATE CSE",
    year: 2000,
    set: null,
    subject: "Databases",
    topic: "B Tree",
    subtopic: null,
    questionNumber: "1",
    questionType: type,
    marks: 2,
    optionsPresent: labels.length > 0,
    optionLabels: labels,
    imageUrl: "/images/test-q.png",
    sourcePages: [1],
    verified: false,
  };
}

function entry(
  correct: GradingEntry["correctAnswer"],
  marks: number | null = 2
): GradingEntry {
  return { id: "test-q", questionType: "MCQ", correctAnswer: correct, answerStatus: "verified", marks };
}

describe("MCQ grading", () => {
  const mcq = q("MCQ", ["A", "B", "C", "D"]);

  it("grades an exact label match as correct", () => {
    const g = gradeResponse(mcq, "B", entry("B"));
    expect(g.status).toBe("correct");
    expect(g.marksAwarded).toBe(2);
  });

  it("is case/whitespace tolerant on labels", () => {
    expect(gradeResponse(mcq, " b ", entry("B")).status).toBe("correct");
  });

  it("grades a wrong label as incorrect with zero marks", () => {
    const g = gradeResponse(mcq, "C", entry("B"));
    expect(g.status).toBe("incorrect");
    expect(g.marksAwarded).toBe(0);
    expect(g.marksAvailable).toBe(2);
  });

  it("reports unanswered MCQ as ungradable — never 'incorrect'", () => {
    const g = gradeResponse(mcq, null, entry("B"));
    expect(g.status).toBe("ungradable");
    expect(g.marksAwarded).toBeNull();
  });
});

describe("MSQ grading", () => {
  const msq = q("MSQ", ["A", "B", "C", "D"]);

  it("accepts an exact set regardless of order", () => {
    expect(gradeResponse(msq, ["C", "A"], entry(["A", "C"])).status).toBe("correct");
  });

  it("rejects a superset (no partial credit)", () => {
    expect(gradeResponse(msq, ["A", "B", "C"], entry(["A", "C"])).status).toBe("incorrect");
  });

  it("rejects a subset", () => {
    expect(gradeResponse(msq, ["A"], entry(["A", "C"])).status).toBe("incorrect");
  });
});

describe("NAT grading", () => {
  const nat = q("NAT");

  it("accepts numerically equal values", () => {
    expect(gradeResponse(nat, "42", entry(42)).status).toBe("correct");
    expect(gradeResponse(nat, "42.0", entry(42)).status).toBe("correct");
  });

  it("does NOT accept near-miss values (no invented tolerance)", () => {
    expect(gradeResponse(nat, "42.1", entry(42)).status).toBe("incorrect");
  });

  it("handles negative and decimal answers", () => {
    expect(gradeResponse(nat, "-3.5", entry(-3.5)).status).toBe("correct");
  });

  it("accepts any value inside a stored range answer", () => {
    expect(gradeResponse(nat, "51", entry([50, 52])).status).toBe("correct");
    expect(gradeResponse(nat, "53", entry([50, 52])).status).toBe("incorrect");
  });
});

describe("ungradable handling (never 'incorrect')", () => {
  it("marks a question with no grading entry as ungradable", () => {
    const g = gradeResponse(q("MCQ", ["A", "B", "C", "D"]), "A", undefined);
    expect(g.status).toBe("ungradable");
    expect(g.marksAwarded).toBeNull();
  });

  it("marks verified-but-null answers as ungradable", () => {
    const g = gradeResponse(q("MCQ", ["A", "B"]), "A", entry(null));
    expect(g.status).toBe("ungradable");
  });

  it("never auto-grades DESCRIPTIVE answers", () => {
    const g = gradeResponse(q("DESCRIPTIVE"), "my long answer", entry("anything"));
    expect(g.status).toBe("ungradable");
    expect(g.marksAwarded).toBeNull();
  });

  it("never auto-grades FILL_IN_THE_BLANK or MATCH_THE_FOLLOWING", () => {
    expect(gradeResponse(q("FILL_IN_THE_BLANK"), "x", entry("x")).status).toBe("ungradable");
    expect(gradeResponse(q("MATCH_THE_FOLLOWING"), "1-a", entry("1-a")).status).toBe("ungradable");
  });

  it("never grades UNKNOWN types", () => {
    expect(gradeResponse(q("UNKNOWN"), "A", entry("A")).status).toBe("ungradable");
  });
});
