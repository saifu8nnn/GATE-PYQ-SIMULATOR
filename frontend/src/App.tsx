// App root: loads the local dataset once, validates it, and routes between
// views with plain state (no router dependency — fully offline-friendly).

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DatasetError,
  DatasetManifest,
  DisplayQuestion,
  SessionConfig,
} from "./types";
import { loadDataset } from "./services/dataset";
import { getBookmarks, loadActiveSession, toggleBookmark } from "./services/storage";
import { startSession as buildSession } from "./hooks/useSession";
import Dashboard from "./pages/Dashboard";
import Setup from "./pages/Setup";
import Exam, { SubmitOutcome } from "./pages/Exam";
import Results from "./pages/Results";
import { PersistedSession } from "./services/storage";

type View =
  | { name: "dashboard" }
  | { name: "setup"; mode: SessionConfig["mode"] }
  | { name: "exam" }
  | { name: "results"; outcome: SubmitOutcome };

interface BootState {
  status: "loading" | "ready" | "error";
  manifest?: DatasetManifest;
  error?: DatasetError;
}

export default function App() {
  const [boot, setBoot] = useState<BootState>({ status: "loading" });
  const [view, setView] = useState<View>({ name: "dashboard" });
  const [bookmarks, setBookmarks] = useState<Set<string>>(() => new Set(getBookmarks()));
  const [sessionPersisted, setSessionPersisted] = useState<PersistedSession | null>(null);
  const [sessionConfig, setSessionConfig] = useState<SessionConfig | null>(null);
  // An interrupted session (refresh/close) can be resumed from the dashboard.
  const [resumable] = useState<PersistedSession | null>(() => loadActiveSession());

  useEffect(() => {
    let cancelled = false;
    loadDataset()
      .then((manifest) => {
        if (!cancelled) setBoot({ status: "ready", manifest });
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setBoot({
            status: "error",
            error:
              e instanceof DatasetError
                ? e
                : new DatasetError("Unknown dataset failure", [String(e)]),
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const questions = useMemo(() => boot.manifest?.questions ?? [], [boot.manifest]);

  const handleToggleBookmark = useCallback((qid: string) => {
    const nowBookmarked = toggleBookmark(qid);
    setBookmarks((prev) => {
      const next = new Set(prev);
      if (nowBookmarked) next.add(qid);
      else next.delete(qid);
      return next;
    });
  }, []);

  const startSession = useCallback((config: SessionConfig, pool: DisplayQuestion[]) => {
    const persisted = buildSession(pool, config);
    setSessionConfig(config);
    setSessionPersisted(persisted);
    setView({ name: "exam" });
  }, []);

  if (boot.status === "loading") {
    return (
      <div className="page boot">
        <p>Loading local dataset…</p>
      </div>
    );
  }

  if (boot.status === "error" || !boot.manifest) {
    return (
      <div className="page boot error" data-testid="dataset-error">
        <h1>Dataset failed to load</h1>
        <p>{boot.error?.message}</p>
        {boot.error?.details && (
          <ul>
            {boot.error.details.map((d, i) => (
              <li key={i}>
                <code>{d}</code>
              </li>
            ))}
          </ul>
        )}
        <p>
          Fix the dataset and reload, e.g.{" "}
          <code>python scripts/sync_dataset.py</code>.
        </p>
      </div>
    );
  }

  return (
    <div className="app">
      {view.name === "dashboard" && (
        <Dashboard
          manifest={boot.manifest}
          questions={questions}
          resumable={resumable}
          onResume={() => {
            if (!resumable) return;
            setSessionConfig({
              mode: (resumable.mode as SessionConfig["mode"]) || "mixed",
              filterLabel: resumable.filterLabel || "Resumed session",
              timed: resumable.timed,
              durationSec: resumable.durationSec,
              shuffled: resumable.shuffled,
              questionCount: null,
            });
            setSessionPersisted(resumable);
            setView({ name: "exam" });
          }}
          onStart={(mode) => setView({ name: "setup", mode })}
          onBookmarks={() => setView({ name: "setup", mode: "mixed" })}
          onDataSettings={() => setView({ name: "setup", mode: "mixed" })}
        />
      )}

      {view.name === "setup" && (
        <Setup
          questions={questions}
          initialMode={view.mode}
          bookmarks={bookmarks}
          onStart={startSession}
          onBack={() => setView({ name: "dashboard" })}
        />
      )}

      {view.name === "exam" && sessionPersisted && sessionConfig && (
        <Exam
          questions={questions}
          persisted={sessionPersisted}
          config={sessionConfig}
          bookmarks={bookmarks}
          onToggleBookmark={handleToggleBookmark}
          onSubmit={(outcome) => setView({ name: "results", outcome })}
          onAbandon={() => setView({ name: "dashboard" })}
        />
      )}

      {view.name === "results" && (
        <Results
          summary={view.outcome.summary}
          reviews={view.outcome.reviews}
          onBack={() => setView({ name: "dashboard" })}
        />
      )}
    </div>
  );
}
