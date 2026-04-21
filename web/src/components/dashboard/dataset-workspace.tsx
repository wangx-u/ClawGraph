"use client";

import { useDeferredValue, useEffect, useMemo, useState } from "react";
import type {
  BuilderReadiness,
  CohortSummary,
  DatasetSnapshot,
  EvalSuite,
  ModelCandidate,
  RouterHandoff,
  TrainingRequest
} from "@/lib/types";
import {
  getDatasetBuilderMeta,
  getDatasetBuilderStage,
  getLatestBuilderSnapshot
} from "@/lib/dataset-flow";
import { readinessLabel } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type DatasetWorkspaceProps = {
  cohorts: CohortSummary[];
  readinessRows: BuilderReadiness[];
  snapshots: DatasetSnapshot[];
  trainingRequests: TrainingRequest[];
  evalSuites: EvalSuite[];
  modelCandidates: ModelCandidate[];
  routerHandoffs: RouterHandoff[];
};

export function DatasetWorkspace({
  cohorts,
  readinessRows,
  snapshots,
  trainingRequests,
  evalSuites,
  modelCandidates,
  routerHandoffs
}: DatasetWorkspaceProps) {
  const defaultBuilder =
    readinessRows.find((row) => row.ready && !snapshots.some((snapshot) => snapshot.builder === row.builder))
      ?.builder ??
    readinessRows[0]?.builder ??
    snapshots[0]?.builder ??
    "";
  const [query, setQuery] = useState("");
  const [selectedBuilder, setSelectedBuilder] = useState(defaultBuilder);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState(
    getLatestBuilderSnapshot(snapshots, defaultBuilder)?.id ?? ""
  );
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

  const readyWithoutSnapshot = useMemo(
    () => readinessRows.filter((row) => row.ready && !snapshots.some((snapshot) => snapshot.builder === row.builder)),
    [readinessRows, snapshots]
  );
  const readyWithHistory = useMemo(
    () => readinessRows.filter((row) => row.ready && snapshots.some((snapshot) => snapshot.builder === row.builder)),
    [readinessRows, snapshots]
  );
  const blockedBuilders = useMemo(
    () => readinessRows.filter((row) => !row.ready),
    [readinessRows]
  );

  useEffect(() => {
    if (selectedSnapshotId && !filteredSnapshots.some((snapshot) => snapshot.id === selectedSnapshotId)) {
      setSelectedSnapshotId(filteredSnapshots[0]?.id ?? "");
    }
  }, [filteredSnapshots, selectedSnapshotId]);

  useEffect(() => {
    if (!readinessRows.length && !snapshots.length) {
      if (selectedBuilder) {
        setSelectedBuilder("");
      }
      return;
    }

    const candidateBuilderIds = new Set([
      ...readinessRows.map((row) => row.builder),
      ...snapshots.map((snapshot) => snapshot.builder)
    ]);

    if (!candidateBuilderIds.has(selectedBuilder)) {
      setSelectedBuilder(
        readyWithoutSnapshot[0]?.builder ??
          readyWithHistory[0]?.builder ??
          blockedBuilders[0]?.builder ??
          snapshots[0]?.builder ??
          ""
      );
    }
  }, [blockedBuilders, readinessRows, readyWithHistory, readyWithoutSnapshot, selectedBuilder, snapshots]);

  const currentSnapshot = filteredSnapshots.find((snapshot) => snapshot.id === selectedSnapshotId);
  const currentLineage = currentSnapshot ? snapshotLineage.get(currentSnapshot.id) : null;
  const currentBuilder =
    readinessRows.find((row) => row.builder === selectedBuilder) ??
    (currentSnapshot ? readinessRows.find((row) => row.builder === currentSnapshot.builder) : null) ??
    readyWithoutSnapshot[0] ??
    readyWithHistory[0] ??
    blockedBuilders[0] ??
    null;
  const currentBuilderMeta = currentBuilder ? getDatasetBuilderMeta(currentBuilder.builder) : null;
  const currentBuilderSnapshots = currentBuilder
    ? snapshots.filter((snapshot) => snapshot.builder === currentBuilder.builder)
    : [];
  const latestBuilderSnapshot = currentBuilder
    ? getLatestBuilderSnapshot(snapshots, currentBuilder.builder)
    : undefined;
  const latestBuilderLineage = latestBuilderSnapshot ? snapshotLineage.get(latestBuilderSnapshot.id) : null;
  const recommendedCohort =
    (latestBuilderSnapshot
      ? cohorts.find((cohort) => cohort.id === latestBuilderSnapshot.cohortId)
      : undefined) ??
    cohorts.find((cohort) => cohort.purpose === "训练") ??
    cohorts[0];
  const builderStage = getDatasetBuilderStage(currentBuilder, snapshots);
  const canExportFirstSnapshot = builderStage === "first_snapshot";
  const canExportNewVersion = builderStage === "new_version";

  return (
    <div className="grid gap-6 xl:grid-cols-[0.92fr_1.08fr]">
      <div className="space-y-6">
        <Card
          action={<span className="text-xs text-[color:var(--text-soft)]">共 {readinessRows.length} 个导出类型</span>}
          eyebrow="当前导出队列"
          title="先完成待导出动作"
          strong
        >
          <div className="space-y-5">
            <div className="space-y-3">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">
                待导出首版快照
              </div>
              {readyWithoutSnapshot.length ? (
                readyWithoutSnapshot.map((row) => {
                  const active = row.builder === currentBuilder?.builder;
                  const meta = getDatasetBuilderMeta(row.builder);
                  return (
                    <button
                      className={
                        active
                          ? "tech-highlight block w-full rounded-[1.15rem] p-4 text-left"
                          : "panel-soft block w-full rounded-[1.15rem] p-4 text-left transition hover:-translate-y-[1px]"
                      }
                      key={row.builder}
                      onClick={() => {
                        setSelectedBuilder(row.builder);
                        setSelectedSnapshotId("");
                      }}
                      type="button"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-medium">{meta.label}</div>
                          <div className="mt-1 text-sm text-[color:var(--text-muted)]">{meta.description}</div>
                          <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                            预计 {row.predictedRecords} 条记录
                          </div>
                        </div>
                        <Badge tone="success">可导出首版</Badge>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="panel-soft rounded-[1.1rem] p-4 text-sm text-[color:var(--text-muted)]">
                  当前没有等待导出首版快照的导出类型。
                </div>
              )}
            </div>

            <div className="space-y-3">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">
                可继续导出新版本
              </div>
              {readyWithHistory.length ? (
                readyWithHistory.map((row) => {
                  const active = row.builder === currentBuilder?.builder;
                  const meta = getDatasetBuilderMeta(row.builder);
                  const historyCount = snapshots.filter((snapshot) => snapshot.builder === row.builder).length;
                  return (
                    <button
                      className={
                        active
                          ? "tech-highlight block w-full rounded-[1.15rem] p-4 text-left"
                          : "panel-soft block w-full rounded-[1.15rem] p-4 text-left transition hover:-translate-y-[1px]"
                      }
                      key={row.builder}
                      onClick={() => {
                        const latestSnapshot = getLatestBuilderSnapshot(snapshots, row.builder);
                        setSelectedBuilder(row.builder);
                        setSelectedSnapshotId(latestSnapshot?.id ?? "");
                      }}
                      type="button"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-medium">{meta.label}</div>
                          <div className="mt-1 text-sm text-[color:var(--text-muted)]">{historyCount} 份历史快照</div>
                        </div>
                        <Badge tone="info">可出新版本</Badge>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="panel-soft rounded-[1.1rem] p-4 text-sm text-[color:var(--text-muted)]">
                  当前没有已经可刷新版本的导出类型。
                </div>
              )}
            </div>

            <div className="space-y-3 border-t border-[color:var(--line)] pt-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">
                阻塞中的导出类型
              </div>
              {blockedBuilders.length ? (
                blockedBuilders.map((row) => {
                  const active = row.builder === currentBuilder?.builder;
                  const meta = getDatasetBuilderMeta(row.builder);
                  return (
                    <button
                      className={
                        active
                          ? "tech-highlight block w-full rounded-[1.15rem] p-4 text-left"
                          : "panel-soft block w-full rounded-[1.15rem] p-4 text-left transition hover:-translate-y-[1px]"
                      }
                      key={row.builder}
                      onClick={() => {
                        setSelectedBuilder(row.builder);
                        setSelectedSnapshotId("");
                      }}
                      type="button"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-medium">{meta.label}</div>
                          <div className="mt-1 text-sm text-[color:var(--text-muted)]">
                            {row.blockers[0] ?? "仍有待补条件"}
                          </div>
                        </div>
                        <Badge tone="warning">阻塞</Badge>
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="panel-soft rounded-[1.1rem] p-4 text-sm text-[color:var(--text-muted)]">
                  当前没有阻塞中的导出类型。
                </div>
              )}
            </div>
          </div>
        </Card>

        <Card
          action={<span className="text-xs text-[color:var(--text-soft)]">共 {filteredSnapshots.length} 份快照</span>}
          eyebrow="历史快照"
          title="需要时再回看谱系"
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
                  const meta = getDatasetBuilderMeta(snapshot.builder);
                  return (
                    <button
                      className={
                        active
                          ? "tech-highlight block w-full rounded-[1.15rem] p-4 text-left"
                          : "panel-soft block w-full rounded-[1.15rem] p-4 text-left transition hover:-translate-y-[1px]"
                      }
                      key={snapshot.id}
                      onClick={() => {
                        setSelectedSnapshotId(snapshot.id);
                        setSelectedBuilder(snapshot.builder);
                      }}
                      type="button"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium">{snapshot.title ?? snapshot.id}</div>
                          <div className="mono mt-1 text-xs text-[color:var(--text-soft)]">{snapshot.id}</div>
                        </div>
                        <Badge tone="info">{meta.label}</Badge>
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
          </div>
        </Card>
      </div>

      <div className="space-y-6">
        {currentBuilder ? (
          <Card eyebrow="当前构建动作" title={currentBuilderMeta?.label ?? currentBuilder.builder} strong>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={currentBuilder.ready ? "success" : "warning"}>
                {readinessLabel(currentBuilder.ready)}
              </Badge>
              <Badge tone={canExportFirstSnapshot ? "success" : canExportNewVersion ? "info" : "warning"}>
                {canExportFirstSnapshot
                  ? "待导出首版快照"
                  : canExportNewVersion
                    ? "可导出新版本"
                    : "先处理 blocker"}
              </Badge>
            </div>
            <p className="mt-4 max-w-3xl text-sm leading-6 text-[color:var(--text-muted)]">
              {currentBuilderMeta?.description}
            </p>
            <div className="mt-4 grid gap-3 xl:grid-cols-3">
              <div className="panel-soft rounded-[1.1rem] p-4">
                <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Step 1 导出类型</div>
                <div className="mt-2 font-medium">{currentBuilderMeta?.label ?? currentBuilder.builder}</div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                  预计 {currentBuilder.predictedRecords} 条记录
                </div>
              </div>
              <div className="panel-soft rounded-[1.1rem] p-4">
                <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Step 2 来源批次</div>
                <div className="mt-2 font-medium">{recommendedCohort?.title ?? recommendedCohort?.name ?? "待确认"}</div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                  {recommendedCohort
                    ? `${recommendedCohort.purpose} · 选中 ${recommendedCohort.selectedCount} · 待复核 ${recommendedCohort.reviewCount}`
                    : "当前还没有可回看的来源批次。"}
                </div>
              </div>
              <div className="panel-soft rounded-[1.1rem] p-4">
                <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Step 3 当前动作</div>
                <div className="mt-2 font-medium">
                  {canExportFirstSnapshot
                    ? "冻结首版快照"
                    : canExportNewVersion
                      ? "判断是否导出新版本"
                      : "先回上游补数据"}
                </div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                  {currentBuilderMeta?.nextAction}
                </div>
              </div>
            </div>
            <div className="mt-4 rounded-2xl bg-white/70 px-4 py-3 text-sm text-[color:var(--text-muted)]">
              {currentBuilder.blockers[0] ??
                (canExportFirstSnapshot
                  ? "当前已经满足首版快照的导出条件，下一步先确认来源批次。"
                  : canExportNewVersion
                    ? `当前已有 ${currentBuilderSnapshots.length} 份历史快照，可决定是否继续导出新版本。`
                    : "当前导出类型还没有明确的下一步。")}
            </div>
            <div className="mt-5 flex flex-wrap gap-3">
              {currentBuilder.ready ? (
                <Button
                  href={
                    latestBuilderSnapshot
                      ? `/datasets/${latestBuilderSnapshot.id}`
                      : recommendedCohort
                        ? `/curation/cohorts/${recommendedCohort.id}`
                        : "/curation/candidates"
                  }
                  variant="primary"
                >
                  {latestBuilderSnapshot ? "打开最近版本" : "确认来源批次"}
                </Button>
              ) : (
                <Button href="/curation/candidates" variant="primary">回到候选池补数据</Button>
              )}
              <Button
                href={
                  recommendedCohort
                    ? `/curation/cohorts/${recommendedCohort.id}`
                    : currentBuilder.ready
                      ? "/flows/build-dataset"
                      : "/supervision"
                }
                variant="secondary"
              >
                {recommendedCohort ? "查看来源批次" : currentBuilder.ready ? "查看导出步骤" : "回到自动判断"}
              </Button>
              {currentBuilder.ready ? (
                <Button
                  href={
                    latestBuilderLineage?.requests.length
                      ? "/training"
                      : latestBuilderSnapshot
                        ? "/evaluation"
                        : "/datasets"
                  }
                  variant="ghost"
                >
                  {latestBuilderLineage?.requests.length
                    ? "查看下游训练"
                    : latestBuilderSnapshot
                      ? "继续接评测"
                      : "留在当前工作区"}
                </Button>
              ) : null}
            </div>
            <div className="mt-4 grid gap-3 lg:grid-cols-3">
              <div className="panel-soft rounded-[1.1rem] p-4">
                <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">最近版本</div>
                <div className="mt-2 font-medium">
                  {latestBuilderSnapshot ? latestBuilderSnapshot.title ?? latestBuilderSnapshot.id : "还没有历史版本"}
                </div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                  {latestBuilderSnapshot
                    ? `${latestBuilderSnapshot.recordCount} 条记录 · ${latestBuilderSnapshot.createdAt}`
                    : "当前 builder 仍在等待首版快照。"}
                </div>
              </div>
              <div className="panel-soft rounded-[1.1rem] p-4">
                <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">下游训练</div>
                <div className="mt-2 font-medium">{latestBuilderLineage?.requests.length ?? 0} 个训练请求</div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                  {latestBuilderLineage?.requests.length
                    ? "最近版本已经接到训练资产，可继续跟踪评测和上线链路。"
                    : "最近版本还没有进入训练请求，适合继续补训练资产。"}
                </div>
              </div>
              <div className="panel-soft rounded-[1.1rem] p-4">
                <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">评测 / 上线</div>
                <div className="mt-2 font-medium">
                  {latestBuilderLineage?.suites.length ?? 0} / {latestBuilderLineage?.handoffs.length ?? 0}
                </div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                  {latestBuilderLineage?.handoffs.length
                    ? "最近版本已经进入上线接替链路。"
                    : latestBuilderLineage?.suites.length
                      ? "最近版本已有评测资产，下一步可继续接上线控制面。"
                      : "最近版本还没有评测和上线资产。"}
                </div>
              </div>
            </div>
          </Card>
        ) : null}

        {currentSnapshot ? (
          <>
            <Card eyebrow="当前历史快照" title={currentSnapshot.title ?? currentSnapshot.id} strong>
              <div className="grid gap-3 md:grid-cols-4">
                <div className="tech-highlight rounded-2xl p-4">
                  <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">导出类型</div>
                  <div className="mt-3 text-2xl font-semibold">{getDatasetBuilderMeta(currentSnapshot.builder).label}</div>
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

            <Card eyebrow="谱系链路" title="这份历史快照是如何进入下游的">
              <div className="grid gap-4 xl:grid-cols-[0.92fr_1.08fr]">
                <div className="space-y-4">
                  <div className="panel-soft rounded-[1.15rem] p-4">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">上游导出就绪度</div>
                    <div className="mt-2 flex items-center gap-2">
                      <div className="text-lg font-semibold">{getDatasetBuilderMeta(currentSnapshot.builder).label}</div>
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
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">仍在等待导出的类型</div>
                    <div className="mt-3 space-y-2">
                      {readyWithoutSnapshot.length ? (
                        readyWithoutSnapshot.slice(0, 3).map((row) => {
                          const meta = getDatasetBuilderMeta(row.builder);
                          return (
                            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700" key={row.builder}>
                              {meta.label}：已就绪，等待首版快照导出
                            </div>
                          );
                        })
                      ) : blockedBuilders.length ? (
                        blockedBuilders.slice(0, 3).map((row) => {
                          const meta = getDatasetBuilderMeta(row.builder);
                          return (
                            <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700" key={row.builder}>
                              {meta.label}：{row.blockers[0] ?? "仍有待补条件"}
                            </div>
                          );
                        })
                      ) : (
                        <div className="text-sm text-[color:var(--text-muted)]">当前没有等待导出的 builder。</div>
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
          <Card eyebrow="历史快照" title="当前没有选中历史快照" strong>
            <div className="panel-soft rounded-[1.15rem] p-4 text-sm text-[color:var(--text-muted)]">
              先处理左侧待导出队列；只有在你明确选中某份历史快照后，这里才会展开它到训练、评测、上线接替的谱系。
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
