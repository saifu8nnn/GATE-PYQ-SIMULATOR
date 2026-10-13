// End-to-end UI tests through the real component tree with a mocked local
// dataset (acceptance items 1, 2, 11, 12, 17): the app loads the dataset,
// filters work, submission counts and grades honestly, and missing images
// produce a diagnostic error state.

import { describe, expect, it, beforeEach, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { DisplayQuestion } from "./types";

function dq(id: string, over: Partial<DisplayQuestion> = {}): DisplayQuestion {
  return {
    id,
    exam: "GATE CSE",
    year: 1999,
    set: null,
    subject: "Databases",
    topic: "B Tree",
    subtopic: null,
    questionNumber: "1",
    questionType: "MCQ",
    marks: 2,
    optionsPresent: true,
    optionLabels: ["A", "B", "C", "D"],
    imageUrl: `/images/${id}.png`,
    sourcePages: [1],
    verified: false,
    ...over,
  };
}

const QUESTIONS: DisplayQuestion[] = [
  dq("q-mcq", { subject: "Databases", topic: "B Tree" }),
  dq("q-msq", { subject: "Databases", topic: "Normalization", questionType: "MSQ" }),
  dq("q-nat", {
    subject: "Algorithms",
    topic: "Trees",
    questionType: "NAT",
    optionsPresent: false,
    optionLabels: [],
  }),
  dq("q-desc", {
    subject: "Algorithms",
    topic: "Greedy",
    questionType: "DESCRIPTIVE",
    optionsPresent: false,
    optionLabels: [],
    year: 1988,
  }),
];

const ANSWERS = {
  answers: [
    { id: "q-mcq", questionType: "MCQ", correctAnswer: "B", marks: 2, answerStatus: "verified" },
    { id: "q-msq", questionType: "MSQ", correctAnswer: ["A", "C"], marks: 2, answerStatus: "verified" },
    { id: "q-nat", questionType: "NAT", correctAnswer: 42, marks: 1, answerStatus: "verified" },
    // q-desc intentionally has NO grading entry → must be ungradable
  ],
};

function mockFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: unknown) => {
      const u = String(url);
      if (u.includes("questions.json")) {
        return {
          ok: true,
          json: async () => ({
            dataset: { name: "validation_pilot", source: "test", totalQuestions: QUESTIONS.length, gradableQuestions: 3 },
            questions: QUESTIONS,
          }),
        } as Response;
      }
      if (u.includes("answers.json")) {
        return { ok: true, json: async () => ANSWERS } as Response;
      }
      return { ok: false, status: 404 } as Response;
    })
  );
}

beforeEach(() => {
  mockFetch();
});

async function boot() {
  const utils = render(<App />);
  await screen.findByTestId("dataset-badge");
  return utils;
}

describe("dataset loading", () => {
  it("loads the local dataset and shows real counts", async () => {
    await boot();
    expect(screen.getByTestId("dataset-badge")).toHaveTextContent("4");
    expect(screen.getByTestId("dataset-badge")).toHaveTextContent("validation_pilot");
  });

  it("shows a diagnostic error state when the dataset file is missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: false, status: 404 }) as Response)
    );
    render(<App />);
    await screen.findByTestId("dataset-error");
    expect(screen.getByTestId("dataset-error")).toHaveTextContent("sync_dataset");
  });
});

describe("filters", () => {
  it("subject filter narrows the available pool", async () => {
    await boot();
    await userEvent.click(screen.getByTestId("mode-subject"));
    await screen.findByTestId("filter-subject");
    await userEvent.selectOptions(screen.getByTestId("filter-subject"), "Algorithms");
    await waitFor(() => {
      expect(screen.getByTestId("setup-summary")).toHaveTextContent("Available questions: 2");
    });
  });
});

describe("full exam flow", () => {
  async function startSession() {
    await boot();
    await userEvent.click(screen.getByTestId("mode-subject"));
    await screen.findByTestId("start-session");
    await userEvent.click(screen.getByTestId("start-session"));
    await screen.findByTestId("btn-save-next");
  }

  it("submits, grades honestly, and shows results (ungradable ≠ incorrect)", async () => {
    await startSession();

    // Q1 (MCQ): pick the correct answer B
    await userEvent.click(screen.getByRole("radio", { name: "(B)" }));
    await userEvent.click(screen.getByTestId("btn-save-next"));

    // Q2 (MSQ): multi-select A + C
    await userEvent.click(screen.getByRole("checkbox", { name: "(A)" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "(C)" }));
    await userEvent.click(screen.getByTestId("btn-save-next"));

    // Q3 (NAT): numeric input
    await userEvent.type(screen.getByRole("textbox"), "42");
    await userEvent.click(screen.getByTestId("btn-save-next"));

    // Q4 (DESCRIPTIVE): type notes, no auto-grading
    await userEvent.type(screen.getByRole("textbox"), "my proof");
    await userEvent.click(screen.getByTestId("btn-save-next"));

    // Submit
    await userEvent.click(screen.getByRole("button", { name: "Submit Exam" }));
    await screen.findByTestId("submit-dialog");
    await userEvent.click(screen.getByTestId("confirm-submit"));

    await screen.findByText("Session results");
    expect(screen.getByText("Correct").previousElementSibling).toHaveTextContent("3");
    expect(screen.getByText("Incorrect").previousElementSibling).toHaveTextContent("0");
    expect(screen.getByText("Could not be graded").previousElementSibling).toHaveTextContent("1");
    // marks: 2 + 2 + 1 = 5 available, 5 awarded
    expect(screen.getByText("Marks").previousElementSibling).toHaveTextContent("5/5");
  });

  it("marks a wrong MCQ as incorrect, not ungradable", async () => {
    await startSession();
    await userEvent.click(screen.getByRole("radio", { name: "(A)" })); // correct is B
    // skip through the rest without answering
    await userEvent.click(screen.getByTestId("btn-save-next"));
    await userEvent.click(screen.getByTestId("btn-save-next"));
    await userEvent.click(screen.getByTestId("btn-save-next"));
    await userEvent.click(screen.getByRole("button", { name: "Submit Exam" }));
    await userEvent.click(screen.getByTestId("confirm-submit"));
    await screen.findByText("Session results");
    expect(screen.getByText("Incorrect").previousElementSibling).toHaveTextContent("1");
  });

  it("timed sessions show a countdown timer", async () => {
    await boot();
    await userEvent.click(screen.getByTestId("mode-subject"));
    await userEvent.selectOptions(screen.getByTestId("setup-timer"), "1800");
    await userEvent.click(screen.getByTestId("start-session"));
    await screen.findByTestId("exam-timer");
    expect(screen.getByTestId("exam-timer")).toHaveTextContent("30:0");
  });
});

describe("image error state", () => {
  it("shows a diagnostic error with the question id when an image is missing", async () => {
    await boot();
    await userEvent.click(screen.getByTestId("mode-subject"));
    await userEvent.click(screen.getByTestId("start-session"));
    const img = await screen.findByAltText(/Question 1/);
    fireEvent.error(img);
    expect(await screen.findByRole("alert")).toHaveTextContent("q-mcq");
  });
});

describe("bookmarks", () => {
  it("bookmarking persists across an app reload", async () => {
    const first = await boot(); // eslint-disable-line @typescript-eslint/no-unused-vars
    await userEvent.click(screen.getByTestId("mode-subject"));
    await userEvent.click(screen.getByTestId("start-session"));
    await userEvent.click(screen.getByTestId("bookmark-toggle"));
    first.unmount();

    mockFetch(); // fresh fetch stub for the "reload"
    render(<App />);
    await screen.findByTestId("dataset-badge");
    // bookmark count on dashboard is 1
    expect(screen.getByText("Bookmarked").previousElementSibling).toHaveTextContent("1");
  });
});
