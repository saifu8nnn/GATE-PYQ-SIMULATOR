// Response controls. The labels offered here are exactly the option labels
// detected in the source PDF (question.optionLabels) — the same labels the
// question image shows. Nothing is ever invented: a question whose labels
// cannot be established is disabled with an explanation.

import { DisplayQuestion, ResponseValue } from "../types";

interface Props {
  question: DisplayQuestion;
  value: ResponseValue;
  onChange: (value: ResponseValue) => void;
  disabled?: boolean;
}

export default function ResponseArea({ question, value, onChange, disabled }: Props) {
  const t = question.questionType;

  if (t === "MCQ") {
    const selected = typeof value === "string" ? value : "";
    if (question.optionLabels.length === 0) return <LabelsUnavailable />;
    return (
      <fieldset className="response-options" disabled={disabled}>
        <legend>Select one option</legend>
        {question.optionLabels.map((label) => (
          <label key={label} className="option-row">
            <input
              type="radio"
              name={`opt-${question.id}`}
              value={label}
              checked={selected === label}
              onChange={() => onChange(label)}
            />
            <span className="option-label">({label})</span>
          </label>
        ))}
      </fieldset>
    );
  }

  if (t === "MSQ") {
    const selected = Array.isArray(value) ? value : [];
    if (question.optionLabels.length === 0) return <LabelsUnavailable />;
    return (
      <fieldset className="response-options" disabled={disabled}>
        <legend>Select one or more options</legend>
        {question.optionLabels.map((label) => (
          <label key={label} className="option-row">
            <input
              type="checkbox"
              value={label}
              checked={selected.includes(label)}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? [...selected, label]
                    : selected.filter((l) => l !== label)
                )
              }
            />
            <span className="option-label">({label})</span>
          </label>
        ))}
      </fieldset>
    );
  }

  if (t === "NAT") {
    return (
      <div className="response-nat">
        <label htmlFor={`nat-${question.id}`}>Enter your answer</label>
        <input
          id={`nat-${question.id}`}
          type="text"
          inputMode="decimal"
          value={typeof value === "string" ? value : ""}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          placeholder="e.g. 42 or 3.14"
        />
      </div>
    );
  }

  if (t === "DESCRIPTIVE" || t === "FILL_IN_THE_BLANK" || t === "MATCH_THE_FOLLOWING") {
    return (
      <div className="response-text">
        <label htmlFor={`txt-${question.id}`}>
          {t === "MATCH_THE_FOLLOWING"
            ? "Your matching (notes — not auto-graded)"
            : "Your answer (notes — not auto-graded)"}
        </label>
        <textarea
          id={`txt-${question.id}`}
          rows={4}
          value={typeof value === "string" ? value : ""}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Write your response. This question type is not auto-graded."
        />
      </div>
    );
  }

  // UNKNOWN (or anything unforeseen): display safely, disable grading.
  return (
    <div className="response-unknown" role="status">
      <p>
        This question's type could not be determined from the source, so no
        response control is available. You can still bookmark it for manual
        practice.
      </p>
    </div>
  );
}

function LabelsUnavailable() {
  return (
    <div className="response-unknown" role="status">
      <p>
        This question is graded by option label, but the source labels could not
        be reliably detected — no response control is offered rather than
        inventing one.
      </p>
    </div>
  );
}
