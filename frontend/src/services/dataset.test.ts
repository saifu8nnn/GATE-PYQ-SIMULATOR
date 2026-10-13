// Dataset validation tests (acceptance items 1, 10, 11): bad records are
// reported, never silently dropped.

import { describe, expect, it } from "vitest";
import { validateManifest } from "./dataset";
import { DisplayQuestion } from "../types";

function dq(overrides: Partial<DisplayQuestion> = {}): DisplayQuestion {
  return {
    id: "gate-cse-1999-q1.25",
    exam: "GATE CSE",
    year: 1999,
    set: null,
    subject: "Databases",
    topic: "B Tree",
    subtopic: null,
    questionNumber: "1.25",
    questionType: "MCQ",
    marks: null,
    optionsPresent: true,
    optionLabels: ["A", "B", "C", "D"],
    imageUrl: "/images/gate-cse-1999-q1.25.png",
    sourcePages: [260],
    verified: false,
    ...overrides,
  };
}

function manifest(questions: unknown) {
  return { dataset: { name: "test" }, questions };
}

describe("validateManifest", () => {
  it("accepts a valid manifest", () => {
    expect(validateManifest(manifest([dq()]))).toEqual([]);
  });

  it("rejects non-objects and missing question lists", () => {
    expect(validateManifest(null).length).toBeGreaterThan(0);
    expect(validateManifest({ dataset: { name: "x" } }).length).toBeGreaterThan(0);
  });

  it("reports duplicate ids", () => {
    const errs = validateManifest(manifest([dq(), dq()]));
    expect(errs.some((e) => e.includes("duplicate id"))).toBe(true);
  });

  it("reports missing required metadata", () => {
    const errs = validateManifest(manifest([dq({ subject: null as never })]));
    expect(errs.some((e) => e.includes("missing subject"))).toBe(true);
  });

  it("reports remote (non-local) image URLs", () => {
    const errs = validateManifest(manifest([dq({ imageUrl: "https://cdn.example.com/x.png" })]));
    expect(errs.some((e) => e.includes("not local"))).toBe(true);
  });

  it("reports MCQ questions without detected option labels", () => {
    const errs = validateManifest(manifest([dq({ optionLabels: [] })]));
    expect(errs.some((e) => e.includes("without option labels"))).toBe(true);
  });

  it("tolerates UNKNOWN question types (explicitly handled upstream)", () => {
    expect(
      validateManifest(manifest([dq({ questionType: "UNKNOWN" as never, optionLabels: [] })]))
    ).toEqual([]);
  });
});
