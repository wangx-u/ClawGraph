"use client";

import { useDeferredValue, useMemo, useState } from "react";
import type { BuilderReadiness, DatasetSnapshot } from "@/lib/types";
import { readinessLabel } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type DatasetWorkspaceProps = {
  readinessRows: BuilderReadiness[];
  snapshots: DatasetSnapshot[];
};

type ReadinessView = "all" | "ready" | "blocked";

const BUILDER_COPY: Record<string, { label: string; description: string; example: string }> = {
  facts: {
    label: "Facts",
    description: "偏原始事实聚合，适合追踪结构闭环与证据保真。",
    example: "示例：checkout-api 5xx 会话里保留 alert、Prometheus、Loki、rollout 和人工反馈的原始事实。"
  },
  sft: {
    label: "SFT",
    description: "用于监督微调的数据快照，强调 request 级可学习样本。",
    example: "示例：从成功 triage 分支抽取 metrics -> logs -> rollout 的工具调用序列，形成 request 级 SFT。"
  },
  preference: {
    label: "Preference",
    description: "用于 pairwise 或 ranking 偏好学习，需要高质量分歧证据。",
    example: "示例：比较“立即回滚 v2.31.9”和“继续观察并扩容”两条分支，由人工选择更优路径。"
  },
  binary_rl: {
    label: "Binary RL",
    description: "用于 run 级策略优化，关注 rollout 护栏和结果归因。",
    example: "示例：把整次 incident run 是否在安全护栏内恢复 SLO，压成一个 run 级 reward。"
  }
};

export function DatasetWorkspace({ readinessRows, snapshots }: DatasetWorkspaceProps) {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<ReadinessView>("all");
  const [selectedBuilder, setSelectedBuilder] = useState(readinessRows[0]?.builder ?? "");
  const [selectedSnapshotId, setSelectedSnapshotId] = useState(snapshots[0]?.id ?? "");
  const deferredQuery = useDeferredValue(query);
  const normalizedQuery = deferredQuery.trim().toLowerCase();

  const filteredBuilders = useMemo(
    () =>
      readinessRows.filter((row) => {
        const matchesView =
          view === "all" ? true : view === "ready" ? row.ready : !row.ready;

        if (!matchesView) {
          return false;
        }

        if (!normalizedQuery) {
          return true;
        }

        return [row.builder, ...row.blockers].join(" ").toLowerCase().includes(normalizedQuery);
      }),
    [normalizedQuery, readinessRows, view]
  );

  const currentBuilder =
    filteredBuilders.find((row) => row.builder === selectedBuilder) ??
    readinessRows.find((row) => row.builder === selectedBuilder) ??
    filteredBuilders[0] ??
    readinessRows[0];

  const snapshotsForBuilder = useMemo(() => {
    if (!currentBuilder) {
      return [];
    }

    return snapshots.filter((snapshot) => snapshot.builder === currentBuilder.builder);
  }, [currentBuilder, snapshots]);

  const selectedSnapshot =
    snapshotsForBuilder.find((snapshot) => snapshot.id === selectedSnapshotId) ??
    snapshots.find((snapshot) => snapshot.id === selectedSnapshotId) ??
    snapshotsForBuilder[0] ??
    snapshots[0];

  const builderCopy = currentBuilder
    ? BUILDER_COPY[currentBuilder.builder] ?? {
        label: currentBuilder.builder,
        description: "当前 Builder 已被真实数据源识别，可以直接进入快照导出与 manifest 检查。"
      }
    : null;

  return (
    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <Card
        action={<span className="text-xs text-[color:var(--text-soft)]">共 {filteredBuilders.length} 个 Builder</span>}
        eyebrow="Builder 工作台"
        title="Readiness 选择器"
        strong
      >
        <div className="space-y-4">
          <div className="rounded-[1.1rem] border border-slate-200 bg-white/85 px-4 py-3 shadow-sm">
            <input
              className="w-full bg-transparent text-sm text-[color:var(--text)] outline-none placeholder:text-[color:var(--text-soft)]"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="按 builder / blocker 搜索"
              value={query}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              ["all", "全部"],
              ["ready", "仅就绪"],
              ["blocked", "仅阻塞"]
            ].map(([id, label]) => (
              <button
                className={
                  view === id
                    ? "rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs text-sky-700"
                    : "rounded-full border border-slate-200 bg-white/85 px-3 py-1.5 text-xs text-[color:var(--text-muted)] hover:bg-sky-50"
                }
                key={id}
                onClick={() => setView(id as ReadinessView)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>

          <div className="space-y-3">
            {filteredBuilders.map((row) => {
              const snapshotCount = snapshots.filter((snapshot) => snapshot.builder === row.builder).length;
              const active = row.builder === currentBuilder?.builder;

              return (
                <button
                  className={
                    active
                      ? "tech-highlight block w-full rounded-[1.2rem] p-4 text-left"
                      : "panel-soft block w-full rounded-[1.2rem] p-4 text-left transition hover:-translate-y-[1px]"
                  }
                  key={row.builder}
                  onClick={() => {
                    setSelectedBuilder(row.builder);
                    setSelectedSnapshotId(
                      snapshots.find((snapshot) => snapshot.builder === row.builder)?.id ?? ""
                    );
                  }}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="mono text-xs text-[color:var(--text-soft)]">{row.builder}</div>
                      <div className="mt-2 text-lg font-medium">{row.predictedRecords} 条预测记录</div>
                      <div className="mt-1 text-sm text-[color:var(--text-muted)]">
                        {snapshotCount} 个快照 · {row.blockers.length ? "存在阻塞项" : "可直接导出"}
                      </div>
                    </div>
                    <Badge tone={row.ready ? "success" : "warning"}>{readinessLabel(row.ready)}</Badge>
                  </div>
                  <div className="mt-3 text-xs text-[color:var(--text-soft)]">
                    {row.blockers[0] ?? "当前 Builder 已满足最小导出条件。"}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      {currentBuilder ? (
        <div className="space-y-6">
          <Card eyebrow="当前 Builder" title={builderCopy?.label ?? currentBuilder.builder} strong>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="tech-highlight rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">状态</div>
                <div className="mt-3 text-2xl font-semibold">{readinessLabel(currentBuilder.ready)}</div>
              </div>
              <div className="panel-soft rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">预测记录</div>
                <div className="mt-3 text-2xl font-semibold">{currentBuilder.predictedRecords}</div>
              </div>
              <div className="panel-soft rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">历史快照</div>
                <div className="mt-3 text-2xl font-semibold">{snapshotsForBuilder.length}</div>
              </div>
            </div>
            <p className="mt-4 text-sm leading-6 text-[color:var(--text-muted)]">
              {builderCopy?.description}
            </p>
            <div className="mt-3 rounded-2xl bg-white/70 px-4 py-3 text-sm text-[color:var(--text-muted)]">
              {builderCopy?.example}
            </div>
            <div className="mt-5 flex flex-wrap gap-3">
              <Button href="/flows/build-dataset" variant="primary">发起导出流程</Button>
              {selectedSnapshot ? (
                <Button href={`/datasets/${selectedSnapshot.id}`} variant="secondary">打开当前快照</Button>
              ) : null}
            </div>
          </Card>

          <Card eyebrow="阻塞与导出" title="Builder 操作抽屉">
            <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
              <div className="space-y-3">
                {currentBuilder.blockers.length ? (
                  currentBuilder.blockers.map((blocker) => (
                    <div
                      className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700"
                      key={blocker}
                    >
                      {blocker}
                    </div>
                  ))
                ) : (
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                    当前 Builder 没有阻塞项，可以直接进入 snapshot 导出。
                  </div>
                )}

                <div className="space-y-3 pt-2">
                  {snapshotsForBuilder.length ? (
                    snapshotsForBuilder.map((snapshot) => {
                      const active = snapshot.id === selectedSnapshot?.id;
                      return (
                        <button
                          className={
                            active
                              ? "tech-highlight block w-full rounded-[1.15rem] p-4 text-left"
                              : "panel-soft block w-full rounded-[1.15rem] p-4 text-left transition hover:-translate-y-[1px]"
                          }
                          key={snapshot.id}
                          onClick={() => setSelectedSnapshotId(snapshot.id)}
                          type="button"
                        >
                          <div className="text-sm font-medium">{snapshot.title ?? snapshot.id}</div>
                          <div className="mono text-xs text-[color:var(--text-soft)]">{snapshot.id}</div>
                          <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                            {snapshot.sampleUnit} · {snapshot.recordCount} 条 · {snapshot.createdAt}
                          </div>
                        </button>
                      );
                    })
                  ) : (
                    <div className="panel-soft rounded-[1.15rem] p-4 text-sm text-[color:var(--text-muted)]">
                      还没有历史快照。完成一次导出后，这里会展示 manifest 和产物路径。
                    </div>
                  )}
                </div>
              </div>

              {selectedSnapshot ? (
                <div className="tech-highlight rounded-[1.25rem] p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">当前快照</div>
                      <div className="mt-2 text-2xl font-semibold">{selectedSnapshot.title ?? selectedSnapshot.id}</div>
                      <div className="mono mt-2 text-xs text-[color:var(--text-soft)]">{selectedSnapshot.id}</div>
                    </div>
                    <Badge tone="info">{selectedSnapshot.builder}</Badge>
                  </div>
                  <div className="mt-5 grid gap-3 md:grid-cols-2">
                    <div className="rounded-2xl bg-white/70 p-4">
                      <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">样本与规模</div>
                      <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                        {selectedSnapshot.sampleUnit} · {selectedSnapshot.recordCount} 条记录
                      </div>
                    </div>
                    <div className="rounded-2xl bg-white/70 p-4">
                      <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">导出位置</div>
                      <div className="mono mt-3 break-all text-sm text-[color:var(--text-muted)]">
                        {selectedSnapshot.outputPath}
                      </div>
                    </div>
                  </div>
                  <div className="mt-5 rounded-2xl bg-white/70 p-4">
                    <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">关联 Cohort</div>
                    <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                      {selectedSnapshot.cohortName ?? selectedSnapshot.cohortId} · 创建于 {selectedSnapshot.createdAt}
                    </div>
                  </div>
                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button href={`/datasets/${selectedSnapshot.id}`} variant="primary">打开详情</Button>
                    <Button href={`/curation/cohorts/${selectedSnapshot.cohortId}`} variant="secondary">查看 Cohort</Button>
                  </div>
                </div>
              ) : null}
            </div>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
