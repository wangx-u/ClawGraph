"use client";

import { useDeferredValue, useMemo, useState } from "react";
import type {
  BuilderReadiness,
  DatasetSnapshot,
  EvalSuite,
  ModelCandidate,
  RouterHandoff,
  TrainingRequest
} from "@/lib/types";
import { readinessLabel } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type DatasetWorkspaceProps = {
  readinessRows: BuilderReadiness[];
  snapshots: DatasetSnapshot[];
  trainingRequests: TrainingRequest[];
  evalSuites: EvalSuite[];
  modelCandidates: ModelCandidate[];
  routerHandoffs: RouterHandoff[];
};

const BUILDER_COPY: Record<string, { label: string; description: string }> = {
  facts: {
    label: "Facts",
    description: "偏原始事实聚合，适合追踪结构闭环与证据保真。"
  },
  sft: {
    label: "SFT",
    description: "用于监督微调的数据快照，强调 request 级可学习样本。"
  },
  preference: {
    label: "Preference",
    description: "用于偏好学习的成对样本，需要高质量分歧证据。"
  },
  binary_rl: {
    label: "Binary RL",
    description: "用于 run 级策略优化，关注 rollout 护栏和结果归因。"
  }
};

export function DatasetWorkspace({
  readinessRows,
  snapshots,
  trainingRequests,
  evalSuites,
  modelCandidates,
  routerHandoffs
}: DatasetWorkspaceProps) {
  const [query, setQuery] = useState("");
  const [selectedSnapshotId, setSelectedSnapshotId] = useState(snapshots[0]?.id ?? "");
  const deferredQuery = useDeferredValue(query);
  const normalizedQuery = deferredQuery.trim().toLowerCase();

  const snapshotLineage = useMemo(() => {
    return new Map(
      snapshots.map((snapshot) => {
        const relatedRequests = trainingRequests.filter((request) => request.datasetSnapshotId === snapshot.id);
        const requestIds = new Set(relatedRequests.map((request) => request.id));
        const relatedCandidates = modelCandidates.filter(
          (candidate) =>
            candidate.datasetSnapshotId === snapshot.id || requestIds.has(candidate.trainingRequestId)
        );
        const candidateIds = new Set(relatedCandidates.map((candidate) => candidate.id));
        const suiteIds = new Set(
          [
            ...evalSuites
              .filter((suite) => suite.datasetSnapshotId === snapshot.id)
              .map((suite) => suite.id),
            ...relatedRequests
              .map((request) => request.evalSuiteId)
              .filter((value): value is string => Boolean(value))
          ]
        );
        const relatedSuites = evalSuites.filter((suite) => suiteIds.has(suite.id));
        const relatedHandoffs = routerHandoffs.filter((handoff) => candidateIds.has(handoff.candidateModelId));

        return [
          snapshot.id,
          {
            requests: relatedRequests,
            suites: relatedSuites,
            candidates: relatedCandidates,
            handoffs: relatedHandoffs
          }
        ];
      })
    );
  }, [evalSuites, modelCandidates, routerHandoffs, snapshots, trainingRequests]);

  const filteredSnapshots = useMemo(
    () =>
      snapshots.filter((snapshot) => {
        if (!normalizedQuery) {
          return true;
        }

        return [
          snapshot.id,
          snapshot.title,
          snapshot.builder,
          snapshot.cohortName,
          snapshot.cohortId,
          snapshot.outputPath
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      }),
    [normalizedQuery, snapshots]
  );

  const currentSnapshot =
    filteredSnapshots.find((snapshot) => snapshot.id === selectedSnapshotId) ??
    snapshots.find((snapshot) => snapshot.id === selectedSnapshotId) ??
    filteredSnapshots[0] ??
    snapshots[0];
  const currentLineage = currentSnapshot ? snapshotLineage.get(currentSnapshot.id) : null;
  const currentBuilder = currentSnapshot
    ? readinessRows.find((row) => row.builder === currentSnapshot.builder)
    : null;
  const readyWithoutSnapshot = readinessRows.filter(
    (row) => row.ready && !snapshots.some((snapshot) => snapshot.builder === row.builder)
  );
  const blockedBuilders = readinessRows.filter((row) => !row.ready);
  const builderCopy = currentSnapshot
    ? BUILDER_COPY[currentSnapshot.builder] ?? {
        label: currentSnapshot.builder,
        description: "当前 builder 已被识别，可继续补齐下游导出与谱系关系。"
      }
    : null;

  return (
    <div className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
      <Card
        action={<span className="text-xs text-[color:var(--text-soft)]">共 {filteredSnapshots.length} 份快照</span>}
        eyebrow="数据快照谱系"
        title="先从数据快照看上下游关系"
        strong
      >
        <div className="space-y-4">
          <div className="rounded-[1.1rem] border border-slate-200 bg-white/85 px-4 py-3 shadow-sm">
            <input
              className="w-full bg-transparent text-sm text-[color:var(--text)] outline-none placeholder:text-[color:var(--text-soft)]"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="按数据快照 / 批次 / 导出类型搜索"
              value={query}
            />
          </div>

          <div className="space-y-3">
            {filteredSnapshots.length ? (
              filteredSnapshots.map((snapshot) => {
                const active = snapshot.id === currentSnapshot?.id;
                const lineage = snapshotLineage.get(snapshot.id);
                return (
                  <button
                    className={
                      active
                        ? "tech-highlight block w-full rounded-[1.2rem] p-4 text-left"
                        : "panel-soft block w-full rounded-[1.2rem] p-4 text-left transition hover:-translate-y-[1px]"
                    }
                    key={snapshot.id}
                    onClick={() => setSelectedSnapshotId(snapshot.id)}
                    type="button"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium">{snapshot.title ?? snapshot.id}</div>
                        <div className="mono mt-1 text-xs text-[color:var(--text-soft)]">{snapshot.id}</div>
                      </div>
                      <Badge tone="info">{snapshot.builder}</Badge>
                    </div>
                    <div className="mt-3 grid gap-2 text-sm text-[color:var(--text-muted)]">
                      <div>来源批次：{snapshot.cohortName ?? snapshot.cohortId}</div>
                      <div>
                        下游资产：训练 {lineage?.requests.length ?? 0} · 验证 {lineage?.suites.length ?? 0} · 上线 {lineage?.handoffs.length ?? 0}
                      </div>
                      <div>{snapshot.recordCount} 条记录 · {snapshot.createdAt}</div>
                    </div>
                  </button>
                );
              })
            ) : (
              <div className="panel-soft rounded-[1.15rem] p-4 text-sm text-[color:var(--text-muted)]">
                当前搜索条件下没有匹配快照。
              </div>
            )}
          </div>

          <div className="space-y-3 border-t border-[color:var(--line)] pt-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">
              已就绪但尚未冻结首版快照
              </div>
            {readyWithoutSnapshot.length ? (
              readyWithoutSnapshot.map((row) => (
                <div className="panel-soft rounded-[1.1rem] p-4" key={row.builder}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                    <div className="font-medium">{row.builder}</div>
                      <div className="mt-1 text-sm text-[color:var(--text-muted)]">{row.predictedRecords} 条预测记录</div>
                    </div>
                    <Badge tone="success">待导出首个快照</Badge>
                  </div>
                </div>
              ))
            ) : (
              <div className="panel-soft rounded-[1.1rem] p-4 text-sm text-[color:var(--text-muted)]">
                当前所有已就绪导出类型都已经至少产出一份数据快照。
              </div>
            )}
          </div>
        </div>
      </Card>

      <div className="space-y-6">
        {currentSnapshot ? (
          <>
            <Card eyebrow="当前快照" title={currentSnapshot.title ?? currentSnapshot.id} strong>
              <div className="grid gap-3 md:grid-cols-4">
                <div className="tech-highlight rounded-2xl p-4">
                  <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">导出类型</div>
                  <div className="mt-3 text-2xl font-semibold">{builderCopy?.label ?? currentSnapshot.builder}</div>
                </div>
                <div className="panel-soft rounded-2xl p-4">
                  <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">记录数</div>
                  <div className="mt-3 text-2xl font-semibold">{currentSnapshot.recordCount}</div>
                </div>
                <div className="panel-soft rounded-2xl p-4">
                  <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">训练请求</div>
                  <div className="mt-3 text-2xl font-semibold">{currentLineage?.requests.length ?? 0}</div>
                </div>
                <div className="panel-soft rounded-2xl p-4">
                  <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">验证 / 上线</div>
                  <div className="mt-3 text-2xl font-semibold">
                    {(currentLineage?.suites.length ?? 0) + (currentLineage?.handoffs.length ?? 0)}
                  </div>
                </div>
              </div>
              <p className="mt-4 text-sm leading-6 text-[color:var(--text-muted)]">{builderCopy?.description}</p>
              <div className="mt-4 grid gap-3 lg:grid-cols-3">
                <div className="panel-soft rounded-[1.1rem] p-4 text-sm text-[color:var(--text-muted)]">
                  上游批次：{currentSnapshot.cohortName ?? currentSnapshot.cohortId}
                </div>
                <div className="panel-soft rounded-[1.1rem] p-4 text-sm text-[color:var(--text-muted)]">
                  输出路径：<span className="mono break-all">{currentSnapshot.outputPath}</span>
                </div>
                <div className="panel-soft rounded-[1.1rem] p-4 text-sm text-[color:var(--text-muted)]">
                  创建时间：{currentSnapshot.createdAt}
                </div>
              </div>
              <div className="mt-5 flex flex-wrap gap-3">
                <Button href={`/datasets/${currentSnapshot.id}`} variant="primary">打开快照详情</Button>
                <Button href={`/curation/cohorts/${currentSnapshot.cohortId}`} variant="secondary">查看上游批次</Button>
              </div>
            </Card>

            <Card eyebrow="谱系链路" title="这份数据快照是如何进入下游的">
              <div className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
                <div className="space-y-4">
                  <div className="panel-soft rounded-[1.15rem] p-4">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">上游导出就绪度</div>
                    <div className="mt-2 flex items-center gap-2">
                      <div className="text-lg font-semibold">{currentSnapshot.builder}</div>
                      {currentBuilder ? (
                        <Badge tone={currentBuilder.ready ? "success" : "warning"}>
                          {readinessLabel(currentBuilder.ready)}
                        </Badge>
                      ) : null}
                    </div>
                    <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                      {currentBuilder?.blockers[0] ?? "当前导出类型没有遗留阻塞项。"}
                    </div>
                  </div>

                  <div className="panel-soft rounded-[1.15rem] p-4">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">还在等待快照的 Blocker</div>
                    <div className="mt-3 space-y-2">
                      {blockedBuilders.length ? (
                        blockedBuilders.slice(0, 3).map((row) => (
                          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700" key={row.builder}>
                            {row.builder}：{row.blockers[0] ?? "仍有待补条件"}
                          </div>
                        ))
                      ) : (
                        <div className="text-sm text-[color:var(--text-muted)]">当前没有阻塞中的 builder。</div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="panel-soft rounded-[1.15rem] p-4">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">训练请求</div>
                    <div className="mt-3 space-y-3">
                      {currentLineage?.requests.length ? (
                        currentLineage.requests.map((request) => (
                          <div className="rounded-2xl bg-white/75 p-4" key={request.id}>
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div className="font-medium">{request.title}</div>
                                <div className="mt-1 text-sm text-[color:var(--text-muted)]">{request.summary}</div>
                              </div>
                              <Button href={`/training/requests/${request.id}`} variant="ghost">详情</Button>
                            </div>
                            <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                              {request.baseModel} · {request.createdAt}
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="text-sm text-[color:var(--text-muted)]">这份数据快照还没有进入训练请求。</div>
                      )}
                    </div>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="panel-soft rounded-[1.15rem] p-4">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">评测资产</div>
                      <div className="mt-3 space-y-3">
                        {currentLineage?.suites.length ? (
                          currentLineage.suites.map((suite) => (
                            <div className="rounded-2xl bg-white/75 p-4" key={suite.id}>
                              <div className="font-medium">{suite.title ?? suite.id}</div>
                              <div className="mt-1 text-sm text-[color:var(--text-muted)]">
                                {suite.kind} · {suite.items} 项
                              </div>
                            </div>
                          ))
                        ) : (
                          <div className="text-sm text-[color:var(--text-muted)]">还没有关联的评测套件。</div>
                        )}
                      </div>
                    </div>

                    <div className="panel-soft rounded-[1.15rem] p-4">
                      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">上线接替资产</div>
                      <div className="mt-3 space-y-3">
                        {currentLineage?.handoffs.length ? (
                          currentLineage.handoffs.map((handoff) => (
                            <div className="rounded-2xl bg-white/75 p-4" key={handoff.id}>
                              <div className="font-medium">{handoff.title}</div>
                              <div className="mt-1 text-sm text-[color:var(--text-muted)]">
                                {handoff.sliceLabel ?? handoff.sliceId} · {handoff.stage}
                              </div>
                            </div>
                          ))
                        ) : (
                          <div className="text-sm text-[color:var(--text-muted)]">还没有关联的 handoff / router 资产。</div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </Card>
          </>
        ) : (
          <Card eyebrow="快照谱系" title="当前还没有历史数据快照" strong>
            <div className="space-y-3">
              <div className="panel-soft rounded-[1.15rem] p-4 text-sm text-[color:var(--text-muted)]">
                可以先从已就绪导出类型发起首个导出，之后这里会按批次到数据快照，再到训练 / 评测 / 交接的顺序显示谱系。
              </div>
              {readyWithoutSnapshot.map((row) => (
                <div className="tech-highlight rounded-[1.15rem] p-4" key={row.builder}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-medium">{row.builder}</div>
                      <div className="mt-1 text-sm text-[color:var(--text-muted)]">{row.predictedRecords} 条预测记录</div>
                    </div>
                    <Badge tone="success">可导出首个快照</Badge>
                  </div>
                </div>
              ))}
              <div className="pt-2">
                <Button href="/flows/build-dataset" variant="primary">发起导出流程</Button>
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
