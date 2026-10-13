// Filter controls built ONLY from metadata that actually exists in the loaded
// dataset. Unknown/missing values are handled explicitly — a filter never
// fabricates options and never crashes on null metadata.

import { useMemo } from "react";
import { DisplayQuestion } from "../types";

export interface FilterValues {
  subject: string; // "" = all
  topic: string; // "" = all
  subtopic: string; // "" = all
  year: string; // "" = all; "range:<min>:<max>" for a range
  questionType: string; // "" = all
  bookmarkedOnly: boolean;
  bookmarks: Set<string>;
}

export function emptyFilters(): FilterValues {
  return {
    subject: "",
    topic: "",
    subtopic: "",
    year: "",
    questionType: "",
    bookmarkedOnly: false,
    bookmarks: new Set(),
  };
}

/** Distinct sorted values of a metadata field, skipping null/unknown. */
function distinct(values: (string | number | null | undefined)[]): string[] {
  return [...new Set(values.filter((v) => v !== null && v !== undefined && v !== "").map(String))].sort();
}

export function applyFilters(questions: DisplayQuestion[], f: FilterValues): DisplayQuestion[] {
  return questions.filter((q) => {
    if (f.subject && q.subject !== f.subject) return false;
    if (f.topic && q.topic !== f.topic) return false;
    if (f.subtopic && q.subtopic !== f.subtopic) return false;
    if (f.questionType && q.questionType !== f.questionType) return false;
    if (f.bookmarkedOnly && !f.bookmarks.has(q.id)) return false;
    if (f.year) {
      if (f.year.startsWith("range:")) {
        const [, a, b] = f.year.split(":");
        const lo = Number(a);
        const hi = Number(b);
        if (q.year === null || q.year < lo || q.year > hi) return false;
      } else if (String(q.year) !== f.year) {
        return false;
      }
    }
    return true;
  });
}

interface Props {
  questions: DisplayQuestion[]; // full dataset (for building option lists)
  value: FilterValues;
  onChange: (next: FilterValues) => void;
}

export default function Filters({ questions, value, onChange }: Props) {
  const subjects = useMemo(() => distinct(questions.map((q) => q.subject)), [questions]);
  const types = useMemo(() => distinct(questions.map((q) => q.questionType)), [questions]);
  const years = useMemo(() => distinct(questions.map((q) => q.year)), [questions]);

  // Topics/subtopics depend on the currently chosen subject (cascade).
  const topics = useMemo(() => {
    const pool = value.subject ? questions.filter((q) => q.subject === value.subject) : questions;
    return distinct(pool.map((q) => q.topic));
  }, [questions, value.subject]);

  const subtopics = useMemo(() => {
    const pool = questions.filter(
      (q) =>
        (!value.subject || q.subject === value.subject) &&
        (!value.topic || q.topic === value.topic)
    );
    return distinct(pool.map((q) => q.subtopic));
  }, [questions, value.subject, value.topic]);

  const set = (patch: Partial<FilterValues>) => onChange({ ...value, ...patch });

  return (
    <div className="filters" role="group" aria-label="Question filters">
      <label>
        Subject
        <select
          data-testid="filter-subject"
          value={value.subject}
          onChange={(e) => set({ subject: e.target.value, topic: "", subtopic: "" })}
        >
          <option value="">All subjects</option>
          {subjects.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>

      <label>
        Topic
        <select
          data-testid="filter-topic"
          value={value.topic}
          disabled={topics.length === 0}
          onChange={(e) => set({ topic: e.target.value, subtopic: "" })}
        >
          <option value="">All topics</option>
          {topics.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      {subtopics.length > 0 && (
        <label>
          Subtopic
          <select
            data-testid="filter-subtopic"
            value={value.subtopic}
            onChange={(e) => set({ subtopic: e.target.value })}
          >
            <option value="">All subtopics</option>
            {subtopics.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      )}

      <label>
        Year
        <select
          data-testid="filter-year"
          value={value.year}
          onChange={(e) => set({ year: e.target.value })}
        >
          <option value="">All years</option>
          {years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </label>

      <label>
        Type
        <select
          data-testid="filter-type"
          value={value.questionType}
          onChange={(e) => set({ questionType: e.target.value })}
        >
          <option value="">All types</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      <label className="checkbox-row">
        <input
          type="checkbox"
          data-testid="filter-bookmarked"
          checked={value.bookmarkedOnly}
          onChange={(e) => set({ bookmarkedOnly: e.target.checked })}
        />
        Bookmarked only
      </label>
    </div>
  );
}
