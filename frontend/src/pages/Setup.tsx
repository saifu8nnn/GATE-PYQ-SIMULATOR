// Practice configuration. Before starting, the user sees exactly what will be
// practised: mode, filters, available count, question count, shuffle and
// timer settings — and can correct everything. Subtopic filtering appears only
// when the metadata actually provides subtopics.

import { useMemo, useState } from "react";
import { DisplayQuestion, SessionConfig } from "../types";
import Filters, { applyFilters, emptyFilters, FilterValues } from "../components/Filters";

interface Props {
  questions: DisplayQuestion[];
  initialMode: SessionConfig["mode"];
  bookmarks: Set<string>;
  onStart: (config: SessionConfig, pool: DisplayQuestion[]) => void;
  onBack: () => void;
}

const MODE_TITLES: Record<SessionConfig["mode"], string> = {
  topic: "Topic-wise practice",
  subtopic: "Subtopic-wise practice",
  subject: "Subject-wise practice",
  year: "Year-wise practice",
  mixed: "Mixed practice",
};

const TIMER_PRESETS = [
  { label: "Untimed", sec: null as number | null },
  { label: "30 minutes", sec: 1800 },
  { label: "1 hour", sec: 3600 },
  { label: "2 hours", sec: 7200 },
];

export default function Setup({ questions, initialMode, bookmarks, onStart, onBack }: Props) {
  const [mode, setMode] = useState<SessionConfig["mode"]>(initialMode);
  const [filters, setFilters] = useState<FilterValues>(emptyFilters());
  const [countStr, setCountStr] = useState<string>(""); // "" = all
  const [shuffled, setShuffled] = useState(false);
  const [timerSec, setTimerSec] = useState<number | null>(null);

  const hasSubtopics = useMemo(
    () => questions.some((q) => q.subtopic !== null && q.subtopic !== ""),
    [questions]
  );

  const pool = useMemo(() => {
    const f = { ...filters, bookmarks };
    return applyFilters(questions, f);
  }, [questions, filters, bookmarks]);

  const requested = countStr === "" ? pool.length : Math.max(1, Math.min(pool.length, Number(countStr) || pool.length));
  const yearRange = useMemo(() => {
    const years = questions.map((q) => q.year).filter((y): y is number => y !== null);
    return years.length ? { min: Math.min(...years), max: Math.max(...years) } : null;
  }, [questions]);

  const filterLabel = describeFilters(filters);

  return (
    <div className="page setup">
      <button type="button" onClick={onBack}>
        ← Back to dashboard
      </button>
      <h1>{MODE_TITLES[mode]}</h1>

      <label className="mode-select">
        Practice mode
        <select
          data-testid="setup-mode"
          value={mode}
          onChange={(e) => setMode(e.target.value as SessionConfig["mode"])}
        >
          <option value="topic">Topic-wise</option>
          {hasSubtopics && <option value="subtopic">Subtopic-wise</option>}
          <option value="subject">Subject-wise</option>
          <option value="year">Year-wise</option>
          <option value="mixed">Mixed</option>
        </select>
      </label>

      <Filters questions={questions} value={filters} onChange={setFilters} />

      {mode === "year" && yearRange && (
        <div className="year-range">
          <label>
            From year
            <input
              type="number"
              data-testid="year-from"
              min={yearRange.min}
              max={yearRange.max}
              value={filters.year.startsWith("range:") ? filters.year.split(":")[1] : ""}
              onChange={(e) => {
                const to = filters.year.startsWith("range:") ? filters.year.split(":")[2] : String(yearRange.max);
                setFilters({ ...filters, year: `range:${e.target.value || yearRange.min}:${to}` });
              }}
            />
          </label>
          <label>
            To year
            <input
              type="number"
              data-testid="year-to"
              min={yearRange.min}
              max={yearRange.max}
              value={filters.year.startsWith("range:") ? filters.year.split(":")[2] : ""}
              onChange={(e) => {
                const from = filters.year.startsWith("range:") ? filters.year.split(":")[1] : String(yearRange.min);
                setFilters({ ...filters, year: `range:${from}:${e.target.value || yearRange.max}` });
              }}
            />
          </label>
        </div>
      )}

      <div className="setup-options">
        <label>
          Number of questions (blank = all {pool.length})
          <input
            type="number"
            min={1}
            max={pool.length}
            value={countStr}
            data-testid="setup-count"
            onChange={(e) => setCountStr(e.target.value)}
          />
        </label>

        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={shuffled}
            data-testid="setup-shuffle"
            onChange={(e) => setShuffled(e.target.checked)}
          />
          Shuffle questions
        </label>

        <label>
          Timer
          <select
            data-testid="setup-timer"
            value={timerSec === null ? "" : String(timerSec)}
            onChange={(e) => setTimerSec(e.target.value === "" ? null : Number(e.target.value))}
          >
            {TIMER_PRESETS.map((p) => (
              <option key={p.label} value={p.sec === null ? "" : String(p.sec)}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <section className="setup-summary" aria-label="Session summary" data-testid="setup-summary">
        <h2>Ready to start</h2>
        <ul>
          <li>Mode: {MODE_TITLES[mode]}</li>
          <li>Filter: {filterLabel}</li>
          <li>
            Available questions: <strong>{pool.length}</strong>
          </li>
          <li>
            Questions in this session: <strong>{requested}</strong>
          </li>
          <li>Shuffled: {shuffled ? "yes" : "no"}</li>
          <li>Timer: {timerSec === null ? "untimed" : `${timerSec / 60} minutes`}</li>
          <li>
            Answers: revealed only after submission (client-side answer file is
            never loaded during the exam)
          </li>
        </ul>
        <button
          type="button"
          className="primary"
          data-testid="start-session"
          disabled={pool.length === 0}
          onClick={() => {
            const cfg: SessionConfig = {
              mode,
              filterLabel,
              timed: timerSec !== null,
              durationSec: timerSec,
              shuffled,
              questionCount: countStr === "" ? null : requested,
            };
            onStart(cfg, pool);
          }}
        >
          Start session
        </button>
        {pool.length === 0 && (
          <p className="hint" role="status">
            No questions match the current filters.
          </p>
        )}
      </section>
    </div>
  );
}

function describeFilters(f: FilterValues): string {
  const parts: string[] = [];
  if (f.subject) parts.push(f.subject);
  if (f.topic) parts.push(f.topic);
  if (f.subtopic) parts.push(f.subtopic);
  if (f.year) {
    if (f.year.startsWith("range:")) {
      const [, a, b] = f.year.split(":");
      parts.push(`years ${a}–${b}`);
    } else parts.push(f.year);
  }
  if (f.questionType) parts.push(f.questionType);
  if (f.bookmarkedOnly) parts.push("bookmarked");
  return parts.length ? parts.join(" / ") : "All questions";
}
