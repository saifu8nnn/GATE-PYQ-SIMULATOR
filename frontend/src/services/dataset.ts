// Dataset loading + validation for the offline frontend.
// Fetches local manifests only — no network beyond the static asset origin.

import { DatasetError, DatasetManifest, DisplayQuestion, GradingEntry } from "../types";

const QUESTIONS_URL = "./data/questions.json";
const ANSWERS_URL = "./data/answers.json";

/** Validate a loaded display manifest. Returns a list of problems. */
export function validateManifest(raw: unknown): string[] {
  const errors: string[] = [];
  if (typeof raw !== "object" || raw === null) {
    return ["manifest is not an object"];
  }
  const m = raw as Partial<DatasetManifest>;
  if (!m.dataset || typeof m.dataset.name !== "string") {
    errors.push("missing dataset.name");
  }
  if (!Array.isArray(m.questions)) {
    errors.push("questions is not a list");
    return errors;
  }
  const seen = new Set<string>();
  m.questions.forEach((q: Partial<DisplayQuestion> | null, i: number) => {
    if (typeof q !== "object" || q === null) {
      errors.push(`question[${i}] is not an object`);
      return;
    }
    const qid = q.id ?? `<#${i}>`;
    if (!q.id || typeof q.id !== "string") errors.push(`question[${i}] missing id`);
    else if (seen.has(q.id)) errors.push(`duplicate id: ${q.id}`);
    else seen.add(q.id);
    if (typeof q.year !== "number") errors.push(`${qid}: year is not a number`);
    if (!q.subject) errors.push(`${qid}: missing subject`);
    if (!q.questionType) errors.push(`${qid}: missing questionType`);
    if (!q.imageUrl || typeof q.imageUrl !== "string") {
      errors.push(`${qid}: missing imageUrl`);
    } else if (!q.imageUrl.startsWith("/images/")) {
      errors.push(`${qid}: imageUrl not local: ${q.imageUrl}`);
    }
    if (q.questionType === "MCQ" && (!q.optionLabels || q.optionLabels.length < 2)) {
      errors.push(`${qid}: MCQ without option labels`);
    }
    if (q.questionType === "MSQ" && (!q.optionLabels || q.optionLabels.length < 2)) {
      errors.push(`${qid}: MSQ without option labels`);
    }
  });
  return errors;
}

/** Load and validate the display manifest. Throws DatasetError on failure. */
export async function loadDataset(): Promise<DatasetManifest> {
  let res: Response;
  try {
    res = await fetch(QUESTIONS_URL);
  } catch (e) {
    throw new DatasetError("Could not read the local dataset file", [String(e)]);
  }
  if (!res.ok) {
    throw new DatasetError(`Dataset file missing (HTTP ${res.status})`, [
      `Expected ${QUESTIONS_URL} next to the app. Run: python scripts/sync_dataset.py`,
    ]);
  }
  let raw: unknown;
  try {
    raw = await res.json();
  } catch (e) {
    throw new DatasetError("Dataset file is not valid JSON", [String(e)]);
  }
  const errors = validateManifest(raw);
  if (errors.length > 0) {
    throw new DatasetError("Dataset failed validation", errors);
  }
  return raw as DatasetManifest;
}

/**
 * Load the grading manifest lazily — only when a session is submitted, so an
 * active exam never downloads answers. Returns a map id -> entry.
 */
export async function loadGradingEntries(): Promise<Map<string, GradingEntry>> {
  const map = new Map<string, GradingEntry>();
  let res: Response;
  try {
    res = await fetch(ANSWERS_URL);
  } catch {
    return map; // no grading file → everything ungradable, never a crash
  }
  if (!res.ok) return map;
  try {
    const raw = (await res.json()) as { answers?: GradingEntry[] };
    for (const entry of raw.answers ?? []) {
      if (entry && typeof entry.id === "string" && entry.answerStatus === "verified") {
        map.set(entry.id, entry);
      }
    }
  } catch {
    // corrupt answers file → treat as no grading data
  }
  return map;
}
