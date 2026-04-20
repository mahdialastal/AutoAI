import type { RunDetail } from "@/api/client";
import { Card, CardBody, CardHeader } from "./ui";
import { ShortCard } from "./ShortCard";

export function ShortsGrid({ run }: { run: RunDetail }) {
  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold tracking-tight text-neutral-100">
            {run.source_label || run.run_folder}
          </h2>
          <p className="mt-0.5 truncate text-xs text-neutral-500">
            {run.shorts.length} short{run.shorts.length === 1 ? "" : "s"} · {run.run_folder}
          </p>
        </div>
      </CardHeader>
      <CardBody>
        {run.shorts.length === 0 ? (
          <p className="py-12 text-center text-sm text-neutral-500">
            No shorts in this run.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {run.shorts.map((s, i) => (
              <ShortCard key={s.file} short={s} index={i} />
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
