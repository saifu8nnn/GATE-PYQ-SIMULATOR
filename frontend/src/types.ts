// Shared types for the offline GATE CSE PYQ practice app.
// Mirrors DATASET_CONTRACT.md — the UI depends only on these shapes.

/** A question as served by the display manifest (never contains answers). */
export interface DisplayQuestion {
  id: string;
  exam: string | null;
  year: number | null;
  set: string | null;
  subject: string | null;
  topic: string | null;
  subtopic: string | null;
  questionNumber: string | null;
  questionType: QuestionType;
  marks: number | null;
  optionsPresent: boolean;
  optionLabels: string[];
  imageUrl: string;
  sourcePages: number[];
  verified: boolean;
}

export type QuestionType =
  | "MCQ"
  | "MSQ"
  | "NAT"
  | "DESCRIPTIVE"
  | "FILL_IN_THE_BLANK"
  | "MATCH_THE_FOLLOWING"
  | "UNKNOWN";

export interface GradingEntry {
  id: string;
  questionType: QuestionType;
  correctAnswer: string | string[] | number | number[] | boolean | null;
  marks: number | null;
  answerStatus: "verified";
}

export interface DatasetManifest {
  dataset: {
    name: string;
    source: string;
    totalQuestions: number;
    gradableQuestions: number;
  };
  questions: DisplayQuestion[];
}

/** User response. Shape depends on question type. */
export type ResponseValue = string | string[] | null;

export interface QuestionResponse {
  value: ResponseValue;
  saved: boolean; // persisted via Save & Next (vs. draft while typing)
}

/** The five GATE palette states. */
export type PaletteState =
  | "not_visited"
  | "not_answered" // visited, no response
  | "answered"
  | "marked" // marked, no response
  | "answered_marked"; // response retained AND marked

export type GradeStatus = "correct" | "incorrect" | "ungradable";

export interface GradeResult {
  status: GradeStatus;
  reason?: string; // for 'ungradable'
  marksAwarded: number | null; // number only when graded and marks known
  marksAvailable: number | null;
}

/** One graded question in the results/review screen. */
export interface QuestionReview {
  question: DisplayQuestion;
  response: ResponseValue;
  graded: boolean;
  grade: GradeResult | null;
  correctAnswer: string | string[] | number | number[] | boolean | null | undefined;
}

export interface SessionSummary {
  id: string;
  startedAt: string;
  submittedAt: string;
  mode: string;
  filterLabel: string;
  totalQuestions: number;
  attempted: number;
  correct: number;
  incorrect: number;
  ungradable: number;
  marksAwarded: number | null; // null when any gradable question lacks marks
  marksAvailable: number | null;
  timeUsedSec: number;
  timed: boolean;
}

/** Attempt-history entry for cross-session progress tracking. */
export interface ProgressEntry {
  qid: string;
  status: "correct" | "incorrect" | "ungradable";
  at: string; // ISO timestamp
  sessionId: string;
}

export interface SessionConfig {
  mode: "topic" | "subtopic" | "subject" | "year" | "mixed";
  filterLabel: string;
  timed: boolean;
  durationSec: number | null;
  shuffled: boolean;
  questionCount: number | null; // null = all matching
}

export class DatasetError extends Error {
  constructor(message: string, public readonly details: string[]) {
    super(message);
    this.name = "DatasetError";
  }
}
