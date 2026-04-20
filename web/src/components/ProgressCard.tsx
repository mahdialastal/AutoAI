import { useEffect, useState } from "react";
import { subscribeToRun, type ProgressEvent as PE } from "@/api/client";
import { Badge, Card, CardBody, CardHeader, ProgressBar } from "./ui";

interface Props {
  runFolder: string;
  onDone: () => void;
  onError: (msg: string) => void;
}

const STAGE_LABEL: Record<string, string> = {
  download: "Downloading source",
  transcribe: "Transcribing",
  select: "Picking moments",
  titles: "Writing titles",
  render: "Rendering shorts",
  done: "Done",
  error: "Failed",
};

export function ProgressCard({ runFolder, onDone, onError }: Props) {
  const [events, setEvents] = useState<PE[]>([]);
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    const unsubscribe = subscribeToRun(
      runFolder,
      (ev) => setEvents((prev) => [...prev, ev]),
      (finalStatus, error) => {
        setFinished(true);
        if (finalStatus === "done") onDone();
        else onError(error || `Run ${finalStatus}`);
      },
    );
    return unsubscribe;
  }, [runFolder, onDone, onError]);

  const latest = events[events.length - 1];
  const progress = latest?.progress ?? 0;
  const stage = latest?.stage ?? "pending";
  const label = STAGE_LABEL[stage] ?? stage;
  const tone =
    stage === "done" ? "success" : stage === "error" ? "danger" : "info";

  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold tracking-tight text-neutral-100">Run in progress</h2>
          <p className="mt-0.5 text-xs text-neutral-500">{runFolder}</p>
        </div>
        <Badge tone={tone}>{label}</Badge>
      </CardHeader>
      <CardBody className="space-y-3">
        <ProgressBar value={progress} />
        <p className="text-sm text-neutral-300">
          {latest?.message || "Warming up…"}
        </p>
        {events.length > 1 && (
          <details className="text-xs text-neutral-500">
            <summary className="cursor-pointer select-none hover:text-neutral-300">
              Stage history ({events.length})
            </summary>
            <ul className="mt-2 space-y-1">
              {events.map((e, i) => (
                <li key={i} className="flex items-center gap-2">
                  <span className="w-24 font-mono text-neutral-600">{e.stage}</span>
                  <span className="text-neutral-400">{e.message}</span>
                </li>
              ))}
            </ul>
          </details>
        )}
        {finished && <p className="text-xs text-neutral-500">Stream closed.</p>}
      </CardBody>
    </Card>
  );
}
