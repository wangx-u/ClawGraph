"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { pickPriorityPipelineStage, resolvePipelineStageIdFromPath } from "@/lib/pipeline";
import type { PipelineStageSummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type PipelineNavigatorProps = {
  stages: PipelineStageSummary[];
};

function stageSurface(stage: PipelineStageSummary, active: boolean) {
  if (active) {
    return "border-transparent bg-[linear-gradient(135deg,rgba(50,119,255,0.16),rgba(22,204,179,0.12))]";
  }
  if (stage.blockerCount > 0) {
    return "border-amber-200 bg-amber-50/80";
  }
  if (stage.count > 0) {
    return "border-emerald-200 bg-emerald-50/70";
  }
  return "border-slate-200 bg-white/75";
}

export function PipelineNavigator({ stages }: PipelineNavigatorProps) {
  const pathname = usePathname();
  const priorityStage = pickPriorityPipelineStage(stages);
  const resolvedStageId = resolvePipelineStageIdFromPath(pathname);
  const currentStageId = pathname === "/" ? priorityStage?.id : resolvedStageId ?? priorityStage?.id;
  const currentStage = stages.find((stage) => stage.id === currentStageId) ?? priorityStage ?? stages[0];
  const blockerStageCount = stages.filter((stage) => stage.blockerCount > 0).length;
  const activeStageCount = stages.filter((stage) => stage.count > 0).length;

  if (!currentStage) {
    return null;
  }

  const summaryText =
    currentStage.id === priorityStage?.id
      ? currentStage.blockerCount > 0
        ? currentStage.detail
        : `当前没有更高优先级阻塞，继续推进第 ${currentStage.step} 步。`
      : `更高优先级的阻塞在第 ${priorityStage?.step} 步 · ${priorityStage?.title}。${priorityStage?.detail ?? ""}`;

  return (
    <section className="surface-strong rounded-[1.6rem] p-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-4xl">
          <div className="text-[11px] uppercase tracking-[0.2em] text-sky-700/80">Pipeline Stepper</div>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <h2 className="text-2xl font-semibold">
              第 {currentStage.step} 步 · {currentStage.title}
            </h2>
            <Badge tone={currentStage.tone}>{currentStage.countLabel}</Badge>
            {currentStage.blockerCount > 0 ? <Badge tone="warning">{currentStage.blockerCount} 阻塞</Badge> : null}
          </div>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--text-muted)]">
            {currentStage.description}
          </p>
          <div className="mt-4 flex flex-wrap gap-3">
            <div className="panel-soft rounded-2xl px-4 py-3 text-sm text-[color:var(--text-muted)]">
              已激活阶段：<span className="font-semibold text-[color:var(--text)]">{activeStageCount} / 9</span>
            </div>
            <div className="panel-soft rounded-2xl px-4 py-3 text-sm text-[color:var(--text-muted)]">
              阻塞阶段：<span className="font-semibold text-[color:var(--text)]">{blockerStageCount}</span>
            </div>
            <div className="panel-soft rounded-2xl px-4 py-3 text-sm text-[color:var(--text-muted)]">
              当前说明：<span className="text-[color:var(--text)]">{summaryText}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button href={currentStage.href} variant="primary">
            {currentStage.actionLabel}
          </Button>
          {priorityStage && priorityStage.id !== currentStage.id ? (
            <Button href={priorityStage.href} variant="secondary">
              先处理第 {priorityStage.step} 步
            </Button>
          ) : null}
        </div>
      </div>

      <div className="mt-5 flex gap-3 overflow-x-auto pb-1">
        {stages.map((stage) => {
          const active = stage.id === currentStage.id;
          return (
            <Link
              className={cn(
                "group min-w-[184px] rounded-[1.15rem] border p-4 transition hover:-translate-y-[1px]",
                stageSurface(stage, active)
              )}
              href={stage.href}
              key={stage.id}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">
                    Step {stage.step}
                  </div>
                  <div className="mt-2 text-base font-medium">{stage.title}</div>
                </div>
                <Badge tone={stage.blockerCount > 0 ? "warning" : stage.tone}>
                  {stage.blockerCount > 0 ? `${stage.blockerCount} 阻塞` : stage.countLabel}
                </Badge>
              </div>
              <p className="mt-3 text-sm leading-6 text-[color:var(--text-muted)]">{stage.detail}</p>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
