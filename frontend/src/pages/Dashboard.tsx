// Home dashboard. Every number shown here is computed from the actually
// loaded dataset and saved progress — never hardcoded book totals.

import { useMemo, useState } from "react";
import { DatasetManifest, DisplayQuestion } from "../types";
import {
  PersistedSession,
  getBookmarks,
  getProgress,
  getSessions,
  pruneProgress,
  resetProgress,
} from "../services/storage";

interface Props {
  manifest: DatasetManifest;
  questions: DisplayQuestion[];
  resumable: PersistedSession | null;
  onResume: () => void;
  onStart: (mode: "topic" | "subject" | "year" | "mixed") => void;
  onBookmarks: () => void;
  onDataSettings: () => void;
}

export default function Dashboard({
  manifest,
  questions,
  resumable,
  onResume,
  onStart,
  onBookmarks,
  onDataSettings,
}: Props) {
  const [confirmReset, setConfirmReset] = useState(false);
  const [pruned, setPruned] = useState<number | null>(null);

  const stats = useMemo(() => {
    const bookmarks = getBookmarks();
    const progress = getProgress();
    const sessions = getSessions();
    const subjects = new Set(questions.map((q) => q.subject).filter(Boolean));
    const topics = new Set(questions.map((q) => q.topic).filter(Boolean));
    const years = questions.map((q) => q.year).filter((y): y is number => y !== null);
    const gradable = new Set(
      progress.filter((p) => p.status !== "ungradable").map((p) => p.qid)
    );
    return {
      subjects: subjects.size,
      topics: topics.size,
      yearMin: years.length ? Math.min(...years) : null,
      yearMax: years.length ? Math.max(...years) : null,
      bookmarkCount: bookmarks.length,
      attemptedUnique: gradable.size,
      sessionsCompleted: sessions.length,
      recent: sessions.slice(-5).reverse(),
    };
  }, [questions]);

  const isPilot = manifest.dataset.name === "validation_pilot";

  return (
    <div className="page dashboard">
      <header className="dash-header">
        <h1>GATE CSE PYQ Practice</h1>
        <p className="dataset-badge" data-testid="dataset-badge">
          Dataset loaded: <strong>{manifest.dataset.name}</strong> —{" "}
          <strong>{questions.length}</strong> questions
          {isPilot && (
            <span className="pilot-warning">
              {" "}
              ⚠ Validation pilot subset, NOT the full book collection
            </span>
          )}
        </p>
      </header>

      <section className="stat-grid" aria-label="Dataset and progress statistics">
        <Stat label="Questions available" value={questions.length} />
        <Stat label="Subjects" value={stats.subjects} />
        <Stat label="Topics" value={stats.topics} />
        <Stat
          label="Years covered"
          value={
            stats.yearMin !== null ? `${stats.yearMin}–${stats.yearMax}` : "—"
          }
        />
        <Stat label="Questions answered (attempted)" value={stats.attemptedUnique} />
        <Stat label="Bookmarked" value={stats.bookmarkCount} />
        <Stat label="Sessions completed" value={stats.sessionsCompleted} />
      </section>

      {resumable && (
        <section className="setup-summary" aria-label="Resume session" data-testid="resume-banner">
          <h2>Unfinished session found</h2>
          <p>
            A {resumable.questionIds.length}-question {resumable.mode || "practice"} session
            from {new Date(resumable.startedAt).toLocaleString()} can be resumed — your
            saved responses are intact.
          </p>
          <button type="button" className="primary" data-testid="resume-btn" onClick={onResume}>
            Resume session
          </button>
        </section>
      )}

      <section className="mode-nav" aria-label="Practice modes">
        <h2>Start practising</h2>
        <div className="mode-buttons">
          <button type="button" onClick={() => onStart("topic")} data-testid="mode-topic">
            Topic-wise
          </button>
          <button type="button" onClick={() => onStart("subject")} data-testid="mode-subject">
            Subject-wise
          </button>
          <button type="button" onClick={() => onStart("year")} data-testid="mode-year">
            Year-wise
          </button>
          <button type="button" onClick={() => onStart("mixed")} data-testid="mode-mixed">
            Mixed practice
          </button>
          <button type="button" onClick={onBookmarks} data-testid="mode-bookmarks">
            Bookmarked questions
          </button>
        </div>
        <p className="hint">
          Subtopic filtering appears automatically when the loaded metadata
          provides subtopics.
        </p>
      </section>

      {stats.recent.length > 0 && (
        <section aria-label="Recent sessions">
          <h2>Recent sessions</h2>
          <table className="recent-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Mode</th>
                <th>Score</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {stats.recent.map((s) => (
                <tr key={s.id}>
                  <td>{new Date(s.submittedAt).toLocaleString()}</td>
                  <td>
                    {s.mode} — {s.filterLabel}
                  </td>
                  <td>
                    {s.correct}/{s.attempted} attempted of {s.totalQuestions}
                    {s.ungradable > 0 ? ` (${s.ungradable} ungradable)` : ""}
                  </td>
                  <td>{formatDuration(s.timeUsedSec)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <section className="data-actions" aria-label="Data and settings">
        <button type="button" onClick={onDataSettings}>
          Dataset &amp; data settings
        </button>
        {confirmReset ? (
          <div className="confirm-box" role="alertdialog" aria-label="Confirm reset">
            <p>
              Reset all practice progress and session history? Bookmarks are
              kept. This cannot be undone.
            </p>
            <button
              type="button"
              className="danger"
              data-testid="confirm-reset"
              onClick={() => {
                resetProgress();
                setConfirmReset(false);
                // force a re-render by reloading the page state
                window.location.reload();
              }}
            >
              Yes, reset progress
            </button>
            <button type="button" onClick={() => setConfirmReset(false)}>
              Cancel
            </button>
          </div>
        ) : (
          <button type="button" className="danger-outline" onClick={() => setConfirmReset(true)}>
            Reset practice progress…
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            const valid = new Set(questions.map((q) => q.id));
            setPruned(pruneProgress(valid));
          }}
        >
          Prune stale saved attempts
        </button>
        {pruned !== null && (
          <p className="hint" role="status">
            Removed {pruned} saved attempt(s) whose questions no longer exist.
          </p>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}
