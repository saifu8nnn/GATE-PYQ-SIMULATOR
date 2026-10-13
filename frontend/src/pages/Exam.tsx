// GATE-style exam interface: question header, canonical image, response
// controls, navigation, palette, timer, bookmarking and submission.
// Responses survive every navigation action; nothing is lost on mark/clear.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DisplayQuestion,
  GradeResult,
  GradingEntry,
  QuestionReview,
  SessionConfig,
  SessionSummary,
} from "../types";
import { useSession } from "../hooks/useSession";
import { formatMs, useTimer } from "../hooks/useTimer";
import { loadGradingEntries } from "../services/storage-bridge";
import { gradeResponse } from "../services/grading";
import {
  PersistedSession,
  clearActiveSession,
  recordProgress,
  recordSession,
} from "../services/storage";
import QuestionImage from "../components/QuestionImage";
import ResponseArea from "../components/ResponseArea";
import Palette from "../components/Palette";

export interface SubmitOutcome {
  summary: SessionSummary;
  reviews: QuestionReview[];
}

interface Props {
  questions: DisplayQuestion[];
  persisted: PersistedSession;
  config: SessionConfig;
  bookmarks: Set<string>;
  onToggleBookmark: (qid: string) => void;
  onSubmit: (outcome: SubmitOutcome) => void;
  onAbandon: () => void;
}

export default function Exam({
  questions,
  persisted,
  config,
  bookmarks,
  onToggleBookmark,
  onSubmit,
  onAbandon,
}: Props) {
  const questionsById = useMemo(() => new Map(questions.map((q) => [q.id, q])), [questions]);
  const session = useSession(questionsById, persisted);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const doSubmit = useCallback(async () => {
    if (submitting) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const gradingEntries: Map<string, GradingEntry> = await loadGradingEntries();
      const reviews: QuestionReview[] = session.state.questionIds.map((qid) => {
        const q = questionsById.get(qid)!;
        const response = session.state.responses[qid] ?? null;
        const entry = gradingEntries.get(qid);
        const grade: GradeResult | null = gradeResponse(q, response, entry);
        return {
          question: q,
          response,
          graded: grade.status !== "ungradable",
          grade,
          correctAnswer: entry?.correctAnswer,
        };
      });

      const hasResponse = (r: QuestionReview) =>
        r.response !== null &&
        r.response !== "" &&
        !(Array.isArray(r.response) && r.response.length === 0);
      const attempted = reviews.filter(hasResponse).length;
      const correct = reviews.filter((r) => r.grade?.status === "correct").length;
      const incorrect = reviews.filter((r) => r.grade?.status === "incorrect").length;
      // "Could not be graded" counts only ATTEMPTED questions; unanswered
      // ones are reported in the separate "Unanswered" bucket.
      const ungradable = reviews.filter(
        (r) => hasResponse(r) && r.grade?.status === "ungradable"
      ).length;

      const graded = reviews.filter((r) => r.grade && r.grade.status !== "ungradable");
      const marksKnown = graded.length > 0 && graded.every((r) => r.grade!.marksAvailable !== null);
      const marksAwarded = marksKnown ? graded.reduce((s, r) => s + (r.grade!.marksAwarded ?? 0), 0) : null;
      const marksAvailable = marksKnown ? graded.reduce((s, r) => s + (r.grade!.marksAvailable ?? 0), 0) : null;

      const submittedAt = new Date();
      const timeUsedSec = Math.max(0, Math.round((submittedAt.getTime() - session.state.startedAt) / 1000));

      const summary: SessionSummary = {
        id: `s-${session.state.startedAt}-${Math.random().toString(36).slice(2, 8)}`,
        startedAt: new Date(session.state.startedAt).toISOString(),
        submittedAt: submittedAt.toISOString(),
        mode: config.mode,
        filterLabel: config.filterLabel,
        totalQuestions: reviews.length,
        attempted,
        correct,
        incorrect,
        ungradable,
        marksAwarded,
        marksAvailable,
        timeUsedSec,
        timed: config.timed,
      };

      recordSession(summary);
      recordProgress(
        reviews
          .filter((r) => r.grade !== null)
          .map((r) => ({
            qid: r.question.id,
            status: r.grade!.status as "correct" | "incorrect" | "ungradable",
            at: summary.submittedAt,
            sessionId: summary.id,
          }))
      );

      session.finalize();
      onSubmit({ summary, reviews });
    } catch (e) {
      setSubmitError(`Submission failed: ${e instanceof Error ? e.message : String(e)}`);
      setSubmitting(false);
    }
  }, [submitting, session, questionsById, config, onSubmit]);

  const timer = useTimer(session.state.deadlineMs, () => {
    void doSubmit(); // auto-submit when time expires
  });

  const q = session.currentQuestion;
  const idx = session.state.currentIdx;
  const isBookmarked = q ? bookmarks.has(q.id) : false;

  // Warn 60s before expiry (browser-level, in addition to the visible timer).
  useEffect(() => {
    if (timer.critical && !timer.expired && config.timed) {
      document.title = `⏳ ${formatMs(timer.remainingMs)} left — GATE PYQ`;
    } else {
      document.title = "GATE CSE PYQ Practice — Offline";
    }
  }, [timer.critical, timer.expired, timer.remainingMs, config.timed]);

  if (!q) {
    return (
      <div className="page exam">
        <p role="alert">This session has no questions.</p>
        <button type="button" onClick={onAbandon}>
          Back to dashboard
        </button>
      </div>
    );
  }

  return (
    <div className="page exam">
      <header className="exam-topbar">
        <div className="exam-meta">
          <span data-testid="q-position">
            Question {idx + 1} of {session.state.questionIds.length}
          </span>
          <span>
            {q.year ?? "????"}
            {q.set ? ` · ${q.set}` : ""} · {q.subject ?? "Unknown"} / {q.topic ?? "—"}
          </span>
          <span>
            {q.questionType}
            {q.marks !== null ? ` · ${q.marks} mark${q.marks > 1 ? "s" : ""}` : ""}
          </span>
        </div>
        <div className="exam-topbar-right">
          {config.timed && (
            <span
              className={`exam-timer ${timer.critical ? "critical" : timer.warning ? "warning" : ""}`}
              role="timer"
              aria-label="Time remaining"
              data-testid="exam-timer"
            >
              {formatMs(timer.remainingMs)}
            </span>
          )}
          <button
            type="button"
            data-testid="bookmark-toggle"
            aria-pressed={isBookmarked}
            onClick={() => onToggleBookmark(q.id)}
          >
            {isBookmarked ? "★ Bookmarked" : "☆ Bookmark"}
          </button>
          <button type="button" className="danger-outline" onClick={() => setConfirmOpen(true)}>
            Submit Exam
          </button>
        </div>
      </header>

      {timer.warning && !timer.expired && config.timed && (
        <div className="timer-warning" role="alert" data-testid="timer-warning">
          ⚠ Less than {timer.critical ? "1 minute" : "5 minutes"} remaining — the exam
          submits automatically when time runs out.
        </div>
      )}

      <div className="exam-body">
        <main className="exam-main">
          <QuestionImage question={q} />
          <ResponseArea
            question={q}
            value={session.state.responses[q.id] ?? null}
            onChange={session.setResponse}
            disabled={submitting}
          />

          <nav className="exam-nav" aria-label="Question navigation">
            <button
              type="button"
              onClick={() => session.goTo(idx - 1)}
              disabled={idx === 0}
              data-testid="btn-prev"
            >
              ← Previous
            </button>
            <button
              type="button"
              className="primary"
              onClick={session.saveAndNext}
              data-testid="btn-save-next"
            >
              Save &amp; Next
            </button>
            <button
              type="button"
              onClick={session.markAndNext}
              data-testid="btn-mark-next"
            >
              Mark for Review &amp; Next
            </button>
            {session.state.markedIds.has(q.id) && (
              <button type="button" onClick={session.unmark} data-testid="btn-unmark">
                Remove Review Flag
              </button>
            )}
            <button
              type="button"
              onClick={session.clearResponse}
              data-testid="btn-clear"
            >
              Clear Response
            </button>
          </nav>
          {submitError && (
            <p className="error-text" role="alert">
              {submitError}
            </p>
          )}
        </main>

        <aside className="exam-sidebar">
          <h2>Palette</h2>
          <p className="palette-counts" data-testid="palette-counts">
            Answered: {session.counts.answered} · Unanswered: {session.counts.unanswered} ·
            Marked: {session.counts.marked}
          </p>
          <Palette
            questionIds={session.state.questionIds}
            currentIndex={idx}
            getState={session.paletteState}
            onJump={session.goTo}
          />
        </aside>
      </div>

      {confirmOpen && (
        <div className="modal-backdrop">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Confirm submission"
            data-testid="submit-dialog"
          >
            <h2>Submit exam?</h2>
            <ul>
              <li>Answered: {session.counts.answered}</li>
              <li>Unanswered: {session.counts.unanswered}</li>
              <li>Marked for review: {session.counts.marked}</li>
            </ul>
            <p>Answers will be revealed after submission.</p>
            <button
              type="button"
              className="primary"
              disabled={submitting}
              data-testid="confirm-submit"
              onClick={() => void doSubmit()}
            >
              {submitting ? "Grading…" : "Yes, submit"}
            </button>
            <button type="button" onClick={() => setConfirmOpen(false)} disabled={submitting}>
              Keep working
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** Abandoning an in-progress session clears its persisted slot explicitly. */
export function abandonSession(): void {
  clearActiveSession();
}
