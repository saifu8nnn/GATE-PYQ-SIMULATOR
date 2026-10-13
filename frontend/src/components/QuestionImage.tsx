// The question image IS the question. This viewer never crops or distorts it:
// images render at natural aspect ratio inside a scrollable panel, with
// explicit zoom controls for diagrams/formulae and a diagnostic error state
// (showing the question ID) when a file is missing.

import { useState } from "react";
import { DisplayQuestion } from "../types";

const ZOOM_LEVELS = [0.5, 0.75, 1, 1.5, 2, 3];
const DEFAULT_ZOOM = 2; // rendered PNGs are wide; 2× suits desktop screens

export default function QuestionImage({ question }: { question: DisplayQuestion }) {
  const [zoomIdx, setZoomIdx] = useState(ZOOM_LEVELS.indexOf(DEFAULT_ZOOM));
  const [failed, setFailed] = useState(false);
  const zoom = ZOOM_LEVELS[Math.max(0, zoomIdx)];

  return (
    <div className="q-image-panel">
      <div className="q-image-toolbar" role="toolbar" aria-label="Image zoom controls">
        <button
          type="button"
          onClick={() => setZoomIdx((i) => Math.max(0, i - 1))}
          disabled={zoomIdx === 0}
          aria-label="Zoom out"
        >
          −
        </button>
        <span className="zoom-level" aria-live="polite">
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          onClick={() => setZoomIdx((i) => Math.min(ZOOM_LEVELS.length - 1, i + 1))}
          disabled={zoomIdx === ZOOM_LEVELS.length - 1}
          aria-label="Zoom in"
        >
          +
        </button>
        <button type="button" onClick={() => setZoomIdx(ZOOM_LEVELS.indexOf(1))}>
          Reset
        </button>
      </div>

      <div className="q-image-scroll">
        {failed ? (
          <div className="q-image-error" role="alert">
            <h3>Question image could not be loaded</h3>
            <p>
              Question ID: <code>{question.id}</code>
            </p>
            <p>
              Expected file: <code>public{question.imageUrl}</code>
            </p>
            <p>
              Re-run <code>python scripts/sync_dataset.py</code> to restore missing
              images.
            </p>
          </div>
        ) : (
          <img
            src={question.imageUrl}
            alt={`Question ${question.questionNumber ?? question.id}, ${
              question.subject ?? "unknown subject"
            }, ${question.year ?? "unknown year"}`}
            style={{ width: `${zoom * 100}%`, height: "auto", display: "block" }}
            onError={() => setFailed(true)}
          />
        )}
      </div>
    </div>
  );
}
