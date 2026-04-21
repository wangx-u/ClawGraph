"use client";

import { useDeferredValue, useEffect, useState } from "react";
import type { SessionSummary } from "@/lib/types";
import {
  evidenceDetail,
  evidenceLabel,
  evidenceTone,
  outcomeLabel,
  outcomeTone,
  reviewStatusLabel,
  reviewStatusTone,
  shortId,
  workflowStageTone
} from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FilterBar } from "@/components/ui/filter-bar";

type SessionInboxWorkspaceProps = {
  sessions: SessionSummary[];
};

type SessionView = "all" | "attention" | "ready";
type EvidenceFilter = "all" | "captured" | "curatable" | "evaluable";
type OutcomeFilter = "all" | "failed" | "open" | "succeeded";
type TrajectoryFilter = "all" | "mixed" | "declared";
type DataStateFilter = "all" | "needs_judging" | "candidate_ready" | "dataset_ready";

function runReadyForDataset(run: SessionSummary["runs"][number]) {
  return (
    run.evidenceLevel === "E2" &&
    run.openCount === 0 &&
    Boolean(run.readyBuilders?.length) &&
    !(run.readinessBlockers?.length)
  );
}

function runReadyForCandidate(run: SessionSummary["runs"][number]) {
  return run.openCount === 0 && run.evidenceLevel !== "E0";
}

function sessionMatchesReadyView(session: SessionSummary) {
  return session.runs.some((run) => runReadyForCandidate(run) || runReadyForDataset(run));
}

function sessionMatchesEvidence(session: SessionSummary, filter: EvidenceFilter) {
  if (filter === "all") {
    return true;
  }
  if (filter === "captured") {
    return session.runs.some((run) => run.evidenceLevel === "E0");
  }
  if (filter === "curatable") {
    return session.runs.some((run) => run.evidenceLevel === "E1");
  }
  return session.runs.some((run) => run.evidenceLevel === "E2");
}

function sessionMatchesOutcome(session: SessionSummary, filter: OutcomeFilter) {
  if (filter === "all") {
    return true;
  }
  if (filter === "failed") {
    return session.runs.some((run) => run.outcome === "failed");
  }
  if (filter === "open") {
    return session.runs.some((run) => run.outcome === "open");
  }
  return session.runs.every((run) => run.outcome === "succeeded");
}

function sessionMatchesTrajectory(session: SessionSummary, filter: TrajectoryFilter) {
  if (filter === "all") {
    return true;
  }
  if (filter === "mixed") {
    return session.runs.some((run) => run.declaredRatio < 0.75);
  }
  return session.runs.every((run) => run.declaredRatio >= 0.75);
}

function sessionMatchesDataState(session: SessionSummary, filter: DataStateFilter) {
  if (filter === "all") {
    return true;
  }
  if (filter === "needs_judging") {
    return session.runs.some(
      (run) => run.openCount > 0 || run.evidenceLevel === "E0" || run.reviewStatus === "review"
    );
  }
  if (filter === "candidate_ready") {
    return session.runs.some((run) => runReadyForCandidate(run) && !runReadyForDataset(run));
  }
  return session.runs.some((run) => runReadyForDataset(run));
}

export function SessionInboxWorkspace({ sessions }: SessionInboxWorkspaceProps) {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<SessionView>("all");
  const [evidenceFilter, setEvidenceFilter] = useState<EvidenceFilter>("all");
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("all");
  const [trajectoryFilter, setTrajectoryFilter] = useState<TrajectoryFilter>("all");
  const [dataStateFilter, setDataStateFilter] = useState<DataStateFilter>("all");
  const [selectedSessionId, setSelectedSessionId] = useState(sessions[0]?.id ?? "");
  const [selectedRunId, setSelectedRunId] = useState(sessions[0]?.runs[0]?.id ?? "");
  const deferredQuery = useDeferredValue(query);
  const normalizedQuery = deferredQuery.trim().toLowerCase();
  const filteredSessions = sessions.filter((session) => {
    const matchesView =
      view === "all"
        ? true
        : view === "attention"
        ? session.anomalies.length > 0 || session.runs.some((run) => run.outcome !== "succeeded")
        : sessionMatchesReadyView(session);

    if (!matchesView) {
      return false;
    }

    if (
      !sessionMatchesEvidence(session, evidenceFilter) ||
      !sessionMatchesOutcome(session, outcomeFilter) ||
      !sessionMatchesTrajectory(session, trajectoryFilter) ||
      !sessionMatchesDataState(session, dataStateFilter)
    ) {
      return false;
    }

    if (!normalizedQuery) {
      return true;
    }

    const haystack = [
      session.id,
      session.title,
      session.summary,
      ...session.userIds,
      ...session.anomalies,
      ...session.runs.map((run) => run.id),
      ...session.runs.map((run) => run.title),
      ...session.runs.map((run) => run.summary),
    ]
      .join(" ")
      .toLowerCase();

    return haystack.includes(normalizedQuery);
  });

  const selectedSession = filteredSessions.find((session) => session.id === selectedSessionId) ?? filteredSessions[0];

  useEffect(() => {
    if (!filteredSessions.length) {
      if (selectedSessionId) {
        setSelectedSessionId("");
      }
      if (selectedRunId) {
        setSelectedRunId("");
      }
      return;
    }

    if (!filteredSessions.some((session) => session.id === selectedSessionId)) {
      const nextSession = filteredSessions[0];
      setSelectedSessionId(nextSession.id);
      setSelectedRunId(nextSession.runs[0]?.id ?? "");
      return;
    }

    const currentSession =
      filteredSessions.find((session) => session.id === selectedSessionId) ?? filteredSessions[0];

    if (!currentSession.runs.find((run) => run.id === selectedRunId)) {
      setSelectedRunId(currentSession.runs[0]?.id ?? "");
    }
  }, [filteredSessions, selectedRunId, selectedSessionId]);

  const selectedRun =
    selectedSession?.runs.find((run) => run.id === selectedRunId) ?? selectedSession?.runs[0];
  const selectedRunBlockers = selectedRun?.readinessBlockers ?? selectedRun?.blockers ?? [];

  return (
    <div className="grid gap-6 xl:grid-cols-[0.88fr_1.12fr]">
      <Card
        action={<span className="text-xs text-[color:var(--text-soft)]">共 {filteredSessions.length} 条</span>}
        eyebrow="最近运行"
        title="按任务查看最近运行"
        strong
      >
        <div className="space-y-4">
          <div className="rounded-[1.1rem] border border-slate-200 bg-white/85 px-4 py-3 shadow-sm">
            <input
              className="w-full bg-transparent text-sm text-[color:var(--text)] outline-none placeholder:text-[color:var(--text-soft)]"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="按会话、运行、任务或异常关键词搜索"
              value={query}
            />
          </div>
          <FilterBar
            groups={[
              {
                id: "evidence",
                label: "证据状态",
                value: evidenceFilter,
                options: [
                  { id: "all", label: "全部" },
                  { id: "captured", label: "已采集" },
                  { id: "curatable", label: "可筛选" },
                  { id: "evaluable", label: "可评估" }
                ],
                onChange: (value) => setEvidenceFilter(value as EvidenceFilter)
              },
              {
                id: "outcome",
                label: "运行结果",
                value: outcomeFilter,
                options: [
                  { id: "all", label: "全部" },
                  { id: "failed", label: "有失败" },
                  { id: "open", label: "仍进行中" },
                  { id: "succeeded", label: "全部成功" }
                ],
                onChange: (value) => setOutcomeFilter(value as OutcomeFilter)
              },
              {
                id: "trajectory",
                label: "轨迹可信度",
                value: trajectoryFilter,
                options: [
                  { id: "all", label: "全部" },
                  { id: "mixed", label: "含推断分支" },
                  { id: "declared", label: "显式为主" }
                ],
                onChange: (value) => setTrajectoryFilter(value as TrajectoryFilter)
              },
              {
                id: "data-state",
                label: "数据状态",
                value: dataStateFilter,
                options: [
                  { id: "all", label: "全部" },
                  { id: "needs_judging", label: "待补判断" },
                  { id: "candidate_ready", label: "可入候选" },
                  { id: "dataset_ready", label: "可入数据集" }
                ],
                onChange: (value) => setDataStateFilter(value as DataStateFilter)
              }
            ]}
          />
          <div className="flex flex-wrap gap-2">
            {[
              ["all", "全部"],
              ["attention", "优先处理"],
              ["ready", "可入候选 / 数据集"]
            ].map(([id, label]) => (
              <button
                className={
                  view === id
                    ? "rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs text-sky-700"
                    : "rounded-full border border-slate-200 bg-white/85 px-3 py-1.5 text-xs text-[color:var(--text-muted)] hover:bg-sky-50"
                }
                key={id}
                onClick={() => setView(id as SessionView)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          <div className="space-y-3">
            {filteredSessions.map((session) => {
              const active = session.id === selectedSession?.id;
              return (
                <button
                  className={
                    active
                      ? "tech-highlight block w-full rounded-[1.2rem] p-4 text-left"
                      : "panel-soft block w-full rounded-[1.2rem] p-4 text-left transition hover:-translate-y-[1px]"
                  }
                  key={session.id}
                  onClick={() => {
                    setSelectedSessionId(session.id);
                    setSelectedRunId(session.runs[0]?.id ?? "");
                  }}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="mono text-xs text-[color:var(--text-soft)]">会话 {shortId(session.id)}</div>
                      <div className="mt-2 text-lg font-medium">{session.title ?? `${session.runs.length} 个运行`}</div>
                      <div className="mt-1 text-sm text-[color:var(--text-muted)]">
                        {session.summary ?? `${session.requests} 请求 · ${session.branches} 分支`}
                      </div>
                    </div>
                    <Badge tone={evidenceTone(session.evidenceLevel)}>{evidenceLabel(session.evidenceLevel)}</Badge>
                  </div>
                  {session.anomalies.length ? (
                    <div className="mt-3 text-xs text-amber-700">{session.anomalies[0]}</div>
                  ) : null}
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      {selectedSession ? (
        <div className="space-y-6">
          <Card eyebrow="当前会话" title={selectedSession.title ?? shortId(selectedSession.id)} strong>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="tech-highlight rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">当前阶段</div>
                <div className="mt-3 text-2xl font-semibold">{evidenceLabel(selectedSession.evidenceLevel)}</div>
                <div className="mt-2 text-xs text-[color:var(--text-muted)]">{evidenceDetail(selectedSession.evidenceLevel)}</div>
              </div>
              <div className="panel-soft rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">运行数</div>
                <div className="mt-3 text-2xl font-semibold">{selectedSession.runs.length}</div>
              </div>
              <div className="panel-soft rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">请求数</div>
                <div className="mt-3 text-2xl font-semibold">{selectedSession.requests}</div>
              </div>
              <div className="panel-soft rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">分支数</div>
                <div className="mt-3 text-2xl font-semibold">{selectedSession.branches}</div>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {selectedSession.userIds.map((userId) => (
                <Badge key={userId} tone="info">{userId}</Badge>
              ))}
              <Badge tone="accent">{selectedSession.nextAction ?? "打开运行查看下一步"}</Badge>
            </div>
            {selectedSession.anomalies.length ? (
              <div className="mt-4 space-y-2">
                {selectedSession.anomalies.map((anomaly) => (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700" key={anomaly}>
                    {anomaly}
                  </div>
                ))}
              </div>
            ) : null}
          </Card>

          <Card eyebrow="运行工作区" title="这次会话下一步怎么走">
            <div className="grid gap-4 xl:grid-cols-[0.88fr_1.12fr]">
              <div className="space-y-3">
                {selectedSession.runs.map((run) => {
                  const active = run.id === selectedRun?.id;
                  return (
                    <button
                      className={
                        active
                          ? "tech-highlight block w-full rounded-[1.15rem] p-4 text-left"
                          : "panel-soft block w-full rounded-[1.15rem] p-4 text-left transition hover:-translate-y-[1px]"
                      }
                      key={run.id}
                      onClick={() => setSelectedRunId(run.id)}
                      type="button"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="mono text-xs text-[color:var(--text-soft)]">运行 {shortId(run.id)}</div>
                          <div className="mt-2 font-medium">{run.title ?? run.id}</div>
                          <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                            {run.summary ?? `${run.requestCount} 次请求 · ${run.branchCount} 条分支 · ${run.avgLatency}`}
                          </div>
                        </div>
                        <div className="flex flex-col items-end gap-2">
                          <Badge tone={workflowStageTone(run.stage)}>{run.stageLabel ?? evidenceLabel(run.evidenceLevel)}</Badge>
                          <Badge tone={outcomeTone(run.outcome)}>{outcomeLabel(run.outcome)}</Badge>
                          {run.reviewStatus ? (
                            <Badge tone={reviewStatusTone(run.reviewStatus)}>
                              {reviewStatusLabel(run.reviewStatus)}
                            </Badge>
                          ) : null}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              {selectedRun ? (
                <div className="tech-highlight rounded-[1.25rem] p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">当前运行</div>
                      <div className="mt-2 text-2xl font-semibold">{selectedRun.title ?? selectedRun.id}</div>
                      <div className="mono mt-2 text-xs text-[color:var(--text-soft)]">运行 {shortId(selectedRun.id)}</div>
                      <p className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">
                        {selectedRun.summary ?? selectedRun.stageDetail ?? evidenceDetail(selectedRun.evidenceLevel)}
                      </p>
                    </div>
                    <div className="flex flex-wrap justify-end gap-2">
                      <Badge tone={workflowStageTone(selectedRun.stage)}>{selectedRun.stageLabel ?? evidenceLabel(selectedRun.evidenceLevel)}</Badge>
                      <Badge tone={outcomeTone(selectedRun.outcome)}>{outcomeLabel(selectedRun.outcome)}</Badge>
                      {selectedRun.reviewStatus ? (
                        <Badge tone={reviewStatusTone(selectedRun.reviewStatus)}>
                          {reviewStatusLabel(selectedRun.reviewStatus)}
                        </Badge>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-5 grid gap-3 md:grid-cols-2">
                    <div className="rounded-2xl bg-white/70 p-4">
                      <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">请求闭环</div>
                      <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                        成功 {selectedRun.successCount} · 失败 {selectedRun.failureCount} · 未闭合 {selectedRun.openCount}
                      </div>
                    </div>
                    <div className="rounded-2xl bg-white/70 p-4">
                      <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">数据资产状态</div>
                      <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                        可导出训练格式 {selectedRun.readyBuilders?.length ?? 0} 个 · 判断记录 {selectedRun.artifactCount}
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 rounded-2xl bg-white/70 px-4 py-3 text-sm text-[color:var(--text-muted)]">
                    下一步：{selectedRun.nextAction ?? "进入回放后确认下一步动作"}
                  </div>
                  {selectedRunBlockers.length ? (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {selectedRunBlockers.slice(0, 3).map((blocker) => (
                        <Badge key={blocker} tone="warning">
                          {blocker}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button href={`/sessions/${selectedSession.id}/runs/${selectedRun.id}/replay`} variant="primary">
                      进入回放
                    </Button>
                    <Button href={`/sessions/${selectedSession.id}`} variant="secondary">
                      打开会话详情
                    </Button>
                  </div>
                </div>
              ) : null}
            </div>
          </Card>

          <Card eyebrow="结构异常" title="当前会话需要优先修复的问题">
            {selectedSession.anomalies.length ? (
              <div className="space-y-3">
                {selectedSession.anomalies.map((anomaly) => (
                  <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700" key={anomaly}>
                    {anomaly}
                  </div>
                ))}
              </div>
            ) : (
              <div className="panel-soft rounded-[1.1rem] p-4 text-sm text-[color:var(--text-muted)]">
                当前选中的会话没有高优先级结构异常，可以继续处理运行分诊和下一步动作。
              </div>
            )}
          </Card>
        </div>
      ) : (
        <Card eyebrow="筛选结果" title="当前没有匹配会话" strong>
          <div className="space-y-4">
            <div className="panel-soft rounded-[1.1rem] p-4 text-sm leading-6 text-[color:var(--text-muted)]">
              这组筛选条件下没有会话可查看。先放宽关键词或筛选条件，再继续查看右侧详情。
            </div>
            <Button
              onClick={() => {
                setQuery("");
                setView("all");
                setEvidenceFilter("all");
                setOutcomeFilter("all");
                setTrajectoryFilter("all");
                setDataStateFilter("all");
              }}
              variant="secondary"
            >
              重置筛选
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
