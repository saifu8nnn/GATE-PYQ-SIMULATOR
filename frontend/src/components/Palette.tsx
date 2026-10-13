// Question palette. State is communicated by SHAPE + TEXT LABEL, not colour
// alone (accessible): each state has a distinct glyph and an aria-label.

import { PaletteState } from "../types";

const STATE_META: Record<PaletteState, { glyph: string; label: string; cls: string }> = {
  not_visited: { glyph: "○", label: "Not visited", cls: "pal-nv" },
  not_answered: { glyph: "▢", label: "Visited, not answered", cls: "pal-vu" },
  answered: { glyph: "●", label: "Answered", cls: "pal-an" },
  marked: { glyph: "◆", label: "Marked for review", cls: "pal-mk" },
  answered_marked: { glyph: "◑", label: "Answered and marked", cls: "pal-am" },
};

export function paletteLegend(): { glyph: string; label: string }[] {
  return Object.values(STATE_META).map(({ glyph, label }) => ({ glyph, label }));
}

interface Props {
  questionIds: string[];
  currentIndex: number;
  getState: (qid: string) => PaletteState;
  onJump: (index: number) => void;
}

export default function Palette({ questionIds, currentIndex, getState, onJump }: Props) {
  return (
    <nav className="palette" aria-label="Question palette">
      <ul className="palette-grid">
        {questionIds.map((qid, idx) => {
          const st = getState(qid);
          const meta = STATE_META[st];
          return (
            <li key={qid}>
              <button
                type="button"
                className={`palette-btn ${meta.cls} ${idx === currentIndex ? "pal-current" : ""}`}
                aria-label={`Question ${idx + 1}: ${meta.label}`}
                aria-current={idx === currentIndex ? "true" : undefined}
                onClick={() => onJump(idx)}
              >
                <span className="pal-glyph" aria-hidden="true">
                  {meta.glyph}
                </span>
                <span className="pal-num">{idx + 1}</span>
              </button>
            </li>
          );
        })}
      </ul>
      <ul className="palette-legend" aria-label="Palette legend">
        {Object.entries(STATE_META).map(([key, meta]) => (
          <li key={key}>
            <span aria-hidden="true">{meta.glyph}</span> {meta.label}
          </li>
        ))}
      </ul>
    </nav>
  );
}
