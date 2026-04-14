"use client";

import type { WorkflowLane, WorkflowRun } from "@/lib/types";
import { reviewStatusLabel, reviewStatusTone, workflowStageTone } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type WorkflowBoardProps = {
  lanes: WorkflowLane[];
  runs: WorkflowRun[];
};

export function WorkflowBoard({ lanes, runs }: WorkflowBoardProps) {
  return (
    <div className="space-y-6">
      <div className="grid gap-3 xl:grid-cols-4">
        {lanes.map((lane) => (
          <Card eyebrow="当前流程" key={lane.id} strong title={lane.title}>
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm leading-6 text-[color:var(--text-muted)]">{lane.description}</p>
              <Badge tone={lane.tone}>{lane.count} 条</Badge>
            </div>
            <div className="mt-4 rounded-2xl bg-white/75 px-4 py-3 text-sm text-[color:var(--text-muted)]">
              {lane.detail}
            </div>
            <Button className="mt-5 w-full" href={lane.href} variant="secondary">
              {lane.actionLabel}
            </Button>
          </Card>
        ))}
      </div>

      <Card eyebrow="当前最该处理的运行" title="按阶段整理的真实运行" strong>
        <div className="space-y-3">
          {runs.length ? (
            runs.slice(0, 4).map((run) => (
              <div className="panel-soft rounded-[1.15rem] p-4" key={run.runId}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="mono text-xs text-[color:var(--text-soft)]">
                      {run.sessionId} / {run.runId}
                    </div>
                    <div className="mt-2 text-base font-medium">{run.stageLabel}</div>
                    <p className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">
                      {run.stageDetail}
                    </p>
                  </div>
                  <div className="flex flex-wrap justify-end gap-2">
                    <Badge tone={workflowStageTone(run.stage)}>{run.stageLabel}</Badge>
                    <Badge tone={reviewStatusTone(run.reviewStatus)}>{reviewStatusLabel(run.reviewStatus)}</Badge>
                  </div>
                </div>
                <div className="mt-4 rounded-2xl bg-white/75 px-4 py-3 text-sm text-[color:var(--text-muted)]">
                  下一步：{run.nextAction}
                </div>
                {run.blockers.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {run.blockers.slice(0, 3).map((blocker) => (
                      <Badge key={blocker} tone="warning">
                        {blocker}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-200 px-4 py-8 text-sm text-[color:var(--text-muted)]">
              还没有真实运行进入治理流程。先让 agent 通过 proxy 发起第一条请求。
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
