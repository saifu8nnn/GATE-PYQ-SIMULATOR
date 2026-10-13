// Answer evaluation. Pure functions with no I/O — fully unit-testable.
// Rules follow DATASET_CONTRACT.md §4: never invent tolerance, partial
// credit or negative marking; a missing grading entry means UNGRADABLE,
// never "incorrect".

import {
  DisplayQuestion,
  GradeResult,
  GradingEntry,
  ResponseValue,
} from "../types";

const UNAVAILABLE: Omit<GradeResult, "status"> = {
  marksAwarded: null,
  marksAvailable: null,
};

/** Grade one response against its verified grading entry (if any). */
export function gradeResponse(
  question: DisplayQuestion,
  response: ResponseValue,
  entry: GradingEntry | undefined
): GradeResult {
  const marksAvailable = entry?.marks ?? null;

  // ── No verified answer for this question → ungradable, not incorrect ──────
  if (!entry || entry.correctAnswer === null || entry.correctAnswer === undefined) {
    return {
      status: "ungradable",
      reason: "No verified answer available for this question",
      ...UNAVAILABLE,
    };
  }

  // ── Types that are never auto-graded ──────────────────────────────────────
  const qtype = question.questionType;
  if (
    qtype === "DESCRIPTIVE" ||
    qtype === "FILL_IN_THE_BLANK" ||
    qtype === "MATCH_THE_FOLLOWING" ||
    qtype === "UNKNOWN"
  ) {
    return {
      status: "ungradable",
      reason: `${qtype} questions are not auto-graded — review your response manually`,
      ...UNAVAILABLE,
    };
  }

  // ── Unanswered → not scored at all (never "incorrect": counting an
  // unattempted question as wrong would invent a scoring convention).
  // The UI reports unanswered separately. ────────────────────────────────────
  if (response === null || response === "" || (Array.isArray(response) && response.length === 0)) {
    return {
      status: "ungradable",
      reason: "No response submitted",
      ...UNAVAILABLE,
    };
  }

  if (qtype === "MCQ") {
    const correct = String(entry.correctAnswer).trim().toUpperCase();
    const given = typeof response === "string" ? response.trim().toUpperCase() : "";
    return given === correct
      ? { status: "correct", marksAwarded: marksAvailable, marksAvailable }
      : { status: "incorrect", marksAwarded: 0, marksAvailable };
  }

  if (qtype === "MSQ") {
    // Exact set match; no partial credit without explicit source rules.
    const correct = toLabelSet(entry.correctAnswer);
    const given = toLabelSet(response);
    if (correct.size === 0) {
      return {
        status: "ungradable",
        reason: "Stored MSQ answer has no option labels",
        ...UNAVAILABLE,
      };
    }
    const exact = correct.size === given.size && [...correct].every((l) => given.has(l));
    return exact
      ? { status: "correct", marksAwarded: marksAvailable, marksAvailable }
      : { status: "incorrect", marksAwarded: 0, marksAvailable };
  }

  if (qtype === "NAT") {
    return gradeNat(response, entry.correctAnswer, marksAvailable);
  }

  // Defensive: any other/unknown type is not graded.
  return {
    status: "ungradable",
    reason: `Unsupported question type: ${qtype}`,
    ...UNAVAILABLE,
  };
}

function toLabelSet(v: ResponseValue | GradingEntry["correctAnswer"]): Set<string> {
  const arr = Array.isArray(v) ? v : typeof v === "string" && v.includes(",") ? v.split(",") : [v];
  return new Set(
    arr
      .filter((x) => x !== null && x !== undefined && x !== "")
      .map((x) => String(x).trim().toUpperCase())
  );
}

/**
 * NAT comparison. Numeric answers compare as floats with a tiny epsilon that
 * only absorbs floating-point representation error (1e-9) — NOT a tolerance
 * for near-miss values. Non-numeric stored answers compare as trimmed,
 * case-insensitive strings.
 */
function gradeNat(
  response: ResponseValue,
  correct: GradingEntry["correctAnswer"],
  marksAvailable: number | null
): GradeResult {
  const givenRaw = typeof response === "string" ? response.trim() : String(response ?? "").trim();

  // Range answers stored as [lo, hi]: accept any value inside the range.
  if (Array.isArray(correct) && correct.length === 2 && correct.every((x) => typeof x === "number")) {
    const [lo, hi] = correct as number[];
    const g = Number(givenRaw);
    if (Number.isFinite(g) && g >= lo - 1e-9 && g <= hi + 1e-9) {
      return { status: "correct", marksAwarded: marksAvailable, marksAvailable };
    }
    return { status: "incorrect", marksAwarded: 0, marksAvailable };
  }

  const correctRaw = typeof correct === "number" ? correct : String(correct ?? "").trim();

  if (typeof correctRaw === "number" || /^-?\d+(\.\d+)?$/.test(String(correctRaw))) {
    const g = Number(givenRaw);
    const c = Number(correctRaw);
    if (!Number.isFinite(g)) {
      return { status: "incorrect", marksAwarded: 0, marksAvailable };
    }
    const equal = Math.abs(g - c) < 1e-9;
    return equal
      ? { status: "correct", marksAwarded: marksAvailable, marksAvailable }
      : { status: "incorrect", marksAwarded: 0, marksAvailable };
  }

  // Text-valued NAT answer (rare): case-insensitive trimmed equality.
  const equal =
    givenRaw.toUpperCase() === String(correctRaw).trim().toUpperCase();
  return equal
    ? { status: "correct", marksAwarded: marksAvailable, marksAvailable }
    : { status: "incorrect", marksAwarded: 0, marksAvailable };
}
