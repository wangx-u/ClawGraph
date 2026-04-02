import type { Metric } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

export function MetricCard({ metric }: { metric: Metric }) {
  const bars = [45, 68, 52, 74, 61];

  return (
    <Card className="h-full" strong>
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] tracking-[0.18em] text-[color:var(--text-soft)]">
            {metric.label}
          </div>
          <div className="mt-3 text-3xl font-semibold">{metric.value}</div>
        </div>
        <Badge tone={metric.tone ?? "neutral"}>{metric.change}</Badge>
      </div>
      <div className="mt-5 grid-tech rounded-[1rem] border border-[color:var(--line)] p-3">
        <div className="flex h-14 items-end gap-1.5">
          {bars.map((height, index) => (
            <div
              className="flex-1 rounded-t-full bg-[linear-gradient(180deg,rgba(22,204,179,0.55),rgba(50,119,255,0.78))]"
              key={`${metric.label}-${index}`}
              style={{ height: `${height}%` }}
            />
          ))}
        </div>
      </div>
    </Card>
  );
}
