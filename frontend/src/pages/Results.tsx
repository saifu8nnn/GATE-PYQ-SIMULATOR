// Results + review. Honest reporting: ungradable questions are never counted
// as wrong; marks totals appear only when every graded question has a known
// mark; detailed solutions are stated as unavailable unless the dataset
// actually provides them (it currently does not).

import { useMemo, useState } from "react";
import { QuestionReview, SessionSummary } from "../types";
import QuestionImage from "../components/QuestionImage";

interface Props {
  summary: SessionSummary;
  reviews: QuestionReview[];
  onBack: () => void;
}

function describeResponse(r: QuestionReview): string {
  const v = r.response;
  if (v === null || v === "" || (Array.isArray(v) && v.length === 0)) return "— (not answered)";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

function describeAnswer(v: QuestionReview["correctAnswer"]): string {
  if (v === null || v === undefined) return "—";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

export default function Results({ summary, reviews, onBack }: Props) {
  const [selected, setSelected] = useState(0);
  const accuracy = useMemo(() => {
    const graded = summary.correct + summary.incorrect;
    return graded > 0 ? Math.round((summary.correct / graded) * 100) : null;
  }, [summary]);

  const current = reviews[selected];

  return (
    <div className="page results">
      <h1>Session results</h1>
      <p className="hint">
        {summary.mode} — {summary.filterLabel} · submitted{" "}
        {new Date(summary.submittedAt).toLocaleString()}
      </p>

      <section className="stat-grid" aria-label="Result totals">
        <div className="stat-card">
          <div className="stat-value">{summary.totalQuestions}</div>
          <div className="stat-label">Total questions</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{summary.attempted}</div>
          <div className="stat-label">Attempted</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{summary.totalQuestions - summary.attempted}</div>
          <div className="stat-label">Unanswered</div>
        </div>
        <div className="stat-card ok">
          <div className="stat-value">{summary.correct}</div>
          <div className="stat-label">Correct</div>
        </div>
        <div className="stat-card bad">
          <div className="stat-value">{summary.incorrect}</div>
          <div className="stat-label">Incorrect</div>
        </div>
        <div className="stat-card warn">
          <div className="stat-value">{summary.ungradable}</div>
          <div className="stat-label">Could not be graded</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {summary.marksAwarded !== null && summary.marksAvailable !== null
              ? `${summary.marksAwarded}/${summary.marksAvailable}`
              : "—"}
          </div>
          <div className="stat-label">
            Marks
            {summary.marksAwarded === null ? " (not all questions carry marks)" : ""}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{accuracy !== null ? `${accuracy}%` : "—"}</div>
          <div className="stat-label">Accuracy (graded questions)</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {summary.timeUsedSec >= 60
              ? `${Math.floor(summary.timeUsedSec / 60)}m ${summary.timeUsedSec % 60}s`
              : `${summary.timeUsedSec}s`}
          </div>
          <div className="stat-label">Time used</div>
        </div>
      </section>

      {summary.ungradable > 0 && (
        <p className="hint" role="status">
          {summary.ungradable} question(s) had no verified answer or a type that is not
          auto-graded. They are excluded from the score — they are NOT counted as wrong.
        </p>
      )}

      <section className="review" aria-label="Question-wise review">
        <h2>Review answers</h2>
        <div className="review-nav" role="group" aria-label="Review navigation">
          <button
            type="button"
            onClick={() => setSelected((i) => Math.max(0, i - 1))}
            disabled={selected === 0}
            data-testid="review-prev"
          >
            ← Previous
          </button>
          <span data-testid="review-position">
            {selected + 1} / {reviews.length}
          </span>
          <button
            type="button"
            onClick={() => setSelected((i) => Math.min(reviews.length - 1, i + 1))}
            disabled={selected === reviews.length - 1}
            data-testid="review-next"
          >
            Next →
          </button>
          <select
            data-testid="review-jump"
            value={selected}
            onChange={(e) => setSelected(Number(e.target.value))}
            aria-label="Jump to question"
          >
            {reviews.map((r, i) => (
              <option key={r.question.id} value={i}>
                {i + 1}. {r.question.id} — {r.grade?.status ?? "?"}
              </option>
            ))}
          </select>
        </div>

        {current && (
          <article className="review-item" data-testid="review-item">
            <h3>
              Q{selected + 1}: {current.question.subject ?? "?"} /{" "}
              {current.question.topic ?? "—"} · {current.question.year ?? "?"} ·{" "}
              {current.question.questionType}
            </h3>
            <p>
              Status:{" "}
              <strong className={`grade-${current.grade?.status ?? "unknown"}`}>
                {(current.grade?.status ?? "ungradable").toUpperCase()}
              </strong>
              {current.grade?.reason ? ` — ${current.grade.reason}` : ""}
              {current.grade?.marksAvailable !== null && current.grade?.marksAvailable !== undefined
                ? ` · marks: ${current.grade.marksAwarded ?? 0}/${current.grade.marksAvailable}`
                : ""}
            </p>
            <p>
              Your answer: <strong>{describeResponse(current)}</strong>
            </p>
            {current.graded && (
              <p>
                Correct answer: <strong>{describeAnswer(current.correctAnswer)}</strong>
              </p>
            )}
            <QuestionImage question={current.question} />
            <p className="hint">
              Detailed solution: not available in this dataset (the source books provide
              answer keys only — no solutions are fabricated).
            </p>
          </article>
        )}
      </section>

      <button type="button" className="primary" onClick={onBack} data-testid="results-back">
        Back to dashboard
      </button>
    </div>
  );
}
