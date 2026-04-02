import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import type { JobItem } from "@/lib/types";

type JobTrayProps = {
  jobs: JobItem[];
};

export function JobTray({ jobs }: JobTrayProps) {

  return (
    <Card eyebrow="底部任务栏" title="后台任务">
      <div className="space-y-3">
        {jobs.map((job) => (
          <div className="panel-soft flex items-start justify-between gap-4 rounded-2xl px-4 py-3" key={job.id}>
            <div>
              <div className="font-medium">{job.label}</div>
              <div className="mt-1 text-xs text-[color:var(--text-muted)]">{job.detail}</div>
            </div>
            <Badge tone={genericStatusTone(job.status)}>{genericStatusLabel(job.status)}</Badge>
          </div>
        ))}
      </div>
    </Card>
  );
}
