// Thin async bridge so Exam can lazily load grading entries without importing
// the fetch-based dataset service directly (keeps the dependency direction
// clean and makes mocking in tests trivial).

export { loadGradingEntries } from "./dataset";
