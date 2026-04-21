"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navGroups } from "@/lib/navigation";
import { resolvePipelineStageIdFromPath } from "@/lib/pipeline";
import type { PipelineStageSummary } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

type SidebarNavProps = {
  stages: PipelineStageSummary[];
};

export function SidebarNav({ stages }: SidebarNavProps) {
  const pathname = usePathname();
  const activeStageId = resolvePipelineStageIdFromPath(pathname);
  const stageMap = new Map(stages.map((stage) => [stage.id, stage]));

  return (
    <aside className="hidden w-[280px] shrink-0 xl:block">
      <div className="surface-strong sticky top-4 rounded-[1.6rem] p-4">
        <div className="mb-6">
          <div className="text-[11px] uppercase tracking-[0.22em] text-sky-700/80">ClawGraph</div>
          <div className="mt-2 text-2xl font-semibold">学习数据与模型接替控制面</div>
          <p className="mt-2 text-sm text-[color:var(--text-muted)]">
            按 1-9 阶段闭环推进接入、轨迹、数据集生产、验证与上线接替。
          </p>
        </div>
        <div className="space-y-5">
          {navGroups.map((group) => (
            <div key={group.title}>
              <div className="mb-2 px-2 text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">
                {group.title}
              </div>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const stage = item.stageId ? stageMap.get(item.stageId) : null;
                  const active = item.stageId
                    ? item.stageId === activeStageId
                    : pathname === item.href;
                  return (
                    <Link
                      className={cn(
                        "block rounded-2xl px-3 py-3 transition",
                        active
                          ? "bg-[linear-gradient(135deg,rgba(50,119,255,0.12),rgba(22,204,179,0.09))] text-[color:var(--text)]"
                          : "text-[color:var(--text-muted)] hover:bg-sky-50 hover:text-[color:var(--text)]"
                      )}
                      href={item.href}
                      key={item.href}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="font-medium">{item.title}</div>
                        {stage ? (
                          stage.blockerCount > 0 || stage.count > 0 ? (
                            <Badge
                              className="shrink-0"
                              tone={stage.blockerCount > 0 ? "warning" : stage.tone}
                            >
                              {stage.blockerCount > 0 ? `${stage.blockerCount} 阻塞` : stage.count}
                            </Badge>
                          ) : null
                        ) : null}
                      </div>
                      <div className="mt-1 text-xs text-inherit/80">{item.description}</div>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
