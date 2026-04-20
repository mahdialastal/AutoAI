import { useState } from "react";
import type { ShortInfo } from "@/api/client";
import { Badge, Button, Card } from "./ui";

interface Props {
  short: ShortInfo;
  index: number;
}

export function ShortCard({ short, index }: Props) {
  const [showTranscript, setShowTranscript] = useState(false);

  return (
    <Card className="overflow-hidden">
      <div className="aspect-[9/16] bg-black">
        <video
          src={short.url}
          controls
          playsInline
          preload="metadata"
          className="h-full w-full object-contain"
        />
      </div>
      <div className="space-y-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-neutral-100">{short.title}</p>
            <p className="truncate text-xs text-neutral-500">{short.file}</p>
          </div>
          <Badge tone="neutral">#{index + 1}</Badge>
        </div>
        {short.transcript && (
          <div>
            <button
              type="button"
              onClick={() => setShowTranscript((v) => !v)}
              className="text-xs text-neutral-400 hover:text-neutral-200"
            >
              {showTranscript ? "Hide transcript" : "Show transcript"}
            </button>
            {showTranscript && (
              <p className="mt-1 max-h-32 overflow-y-auto rounded bg-neutral-950/60 p-2 text-xs leading-relaxed text-neutral-300">
                {short.transcript}
              </p>
            )}
          </div>
        )}
        <div className="flex gap-2 pt-1">
          <Button size="sm" variant="secondary" className="flex-1" disabled title="Coming in S3">
            Trim
          </Button>
          <Button size="sm" variant="primary" className="flex-1" disabled title="Coming in S3">
            Publish
          </Button>
        </div>
      </div>
    </Card>
  );
}
