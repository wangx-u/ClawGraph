"use client";

import { useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { resolvePipelineStageIdFromPath } from "@/lib/pipeline";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import type { JobItem } from "@/lib/types";

type JobTrayProps = {
  jobs: JobItem[];
};

export function JobTray({ jobs }: JobTrayProps) {
  const pathname = usePathname();
  const [expanded, setExpanded] = useState(false);
  const currentStageId = resolvePipelineStageIdFromPath(pathname);
  const scopedJobs = useMemo(() => {
    if (pathname === "/") {
      return jobs;
    }
    if (!currentStageId) {
      return jobs;
    }

    return jobs.filter((job) => !job.areas?.length || job.areas.includes(currentStageId));
  }, [currentStageId, jobs, pathname]);
  const visibleJobs = expanded ? scopedJobs : scopedJobs.slice(0, 2);

  if (!jobs.length) {
    return null;
  }

  return (
    <Card
      action={
        scopedJobs.length > 2 ? (
          <Button onClick={() => setExpanded((value) => !value)} variant="ghost">
            {expanded ? "收起" : `展开全部 ${scopedJobs.length} 项`}
          </Button>
        ) : null
      }
      eyebrow="底部任务栏"
      title="后台任务"
    >
      <div className="space-y-3">
        {visibleJobs.length ? visibleJobs.map((job) => (
          <div className="panel-soft flex items-start justify-between gap-4 rounded-2xl px-4 py-3" key={job.id}>
            <div>
              <div className="font-medium">{job.label}</div>
              <div className="mt-1 text-xs text-[color:var(--text-muted)]">{job.detail}</div>
            </div>
            <Badge tone={genericStatusTone(job.status)}>{genericStatusLabel(job.status)}</Badge>
          </div>
        )) : (
          <div className="panel-soft rounded-2xl px-4 py-3 text-sm text-[color:var(--text-muted)]">
            当前阶段没有相关后台任务。
          </div>
        )}
      </div>
    </Card>
  );
}
