import { useCallback, useState } from "react";
import { api, type RunDetail } from "./api/client";
import { SourceForm } from "./components/SourceForm";
import { ProgressCard } from "./components/ProgressCard";
import { ShortsGrid } from "./components/ShortsGrid";
import { Badge } from "./components/ui";

type Phase =
  | { kind: "idle" }
  | { kind: "running"; runFolder: string; source: string }
  | { kind: "done"; run: RunDetail }
  | { kind: "error"; message: string };

export default function App() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });

  const handleStarted = useCallback((runFolder: string, source: string) => {
    setPhase({ kind: "running", runFolder, source });
  }, []);

  const handleDone = useCallback(async () => {
    setPhase((cur) => {
      if (cur.kind !== "running") return cur;
      api
        .getRun(cur.runFolder)
        .then((run) => setPhase({ kind: "done", run }))
        .catch((e: unknown) =>
          setPhase({ kind: "error", message: e instanceof Error ? e.message : String(e) }),
        );
      return cur;
    });
  }, []);

  const handleError = useCallback((message: string) => {
    setPhase({ kind: "error", message });
  }, []);

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-100">
      <header className="border-b border-neutral-900 bg-neutral-950/80 backdrop-blur sticky top-0 z-10">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="flex size-8 items-center justify-center rounded-md bg-sky-500/15 text-sky-400 ring-1 ring-sky-500/30">
              <svg viewBox="0 0 24 24" fill="currentColor" className="size-5">
                <path d="M8 5v14l11-7z" />
              </svg>
            </div>
            <div>
              <h1 className="text-sm font-semibold tracking-tight">MarkSoft AutoShorts</h1>
              <p className="text-xs text-neutral-500">Local-first video → shorts</p>
            </div>
          </div>
          <Badge tone="success">API online</Badge>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-6 py-6">
        <SourceForm
          busy={phase.kind === "running"}
          onStarted={handleStarted}
          onError={handleError}
        />

        {phase.kind === "running" && (
          <ProgressCard
            runFolder={phase.runFolder}
            onDone={handleDone}
            onError={handleError}
          />
        )}

        {phase.kind === "done" && <ShortsGrid run={phase.run} />}

        {phase.kind === "error" && (
          <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-4">
            <p className="text-sm font-medium text-red-200">Something went wrong</p>
            <p className="mt-1 text-xs text-red-300/80">{phase.message}</p>
          </div>
        )}

        <footer className="pt-4 text-xs text-neutral-600">
          Runs land in{" "}
          <code className="rounded bg-neutral-900 px-1.5 py-0.5 text-neutral-400">generated/</code>.
          API docs at <a className="text-sky-400 hover:underline" href="/docs">/docs</a>.
        </footer>
      </main>
    </div>
  );
}
