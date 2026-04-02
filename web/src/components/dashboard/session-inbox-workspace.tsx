"use client";

import { useDeferredValue, useEffect, useState } from "react";
import type { SessionSummary } from "@/lib/types";
import { evidenceTone, outcomeLabel, outcomeTone } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type SessionInboxWorkspaceProps = {
  sessions: SessionSummary[];
};

type SessionView = "all" | "attention" | "e2";

export function SessionInboxWorkspace({ sessions }: SessionInboxWorkspaceProps) {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<SessionView>("all");
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
        : session.evidenceLevel === "E2";

    if (!matchesView) {
      return false;
    }

    if (!normalizedQuery) {
      return true;
    }

    const haystack = [
      session.id,
      ...session.userIds,
      ...session.anomalies,
      ...session.runs.map((run) => run.id),
    ]
      .join(" ")
      .toLowerCase();

    return haystack.includes(normalizedQuery);
  });

  const selectedSession =
    filteredSessions.find((session) => session.id === selectedSessionId) ??
    sessions.find((session) => session.id === selectedSessionId) ??
    filteredSessions[0] ??
    sessions[0];

  useEffect(() => {
    if (!selectedSession) {
      return;
    }
    setSelectedSessionId(selectedSession.id);
    if (!selectedSession.runs.find((run) => run.id === selectedRunId)) {
      setSelectedRunId(selectedSession.runs[0]?.id ?? "");
    }
  }, [selectedRunId, selectedSession]);

  const selectedRun =
    selectedSession?.runs.find((run) => run.id === selectedRunId) ?? selectedSession?.runs[0];

  return (
    <div className="grid gap-6 xl:grid-cols-[0.88fr_1.12fr]">
      <Card
        action={<span className="text-xs text-[color:var(--text-soft)]">共 {filteredSessions.length} 条</span>}
        eyebrow="实时分诊"
        title="会话选择器"
        strong
      >
        <div className="space-y-4">
          <div className="rounded-[1.1rem] border border-slate-200 bg-white/85 px-4 py-3 shadow-sm">
            <input
              className="w-full bg-transparent text-sm text-[color:var(--text)] outline-none placeholder:text-[color:var(--text-soft)]"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="按 session id / run id / user / anomaly 搜索"
              value={query}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              ["all", "全部"],
              ["attention", "待关注"],
              ["e2", "仅 E2"]
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
                      <div className="mono text-xs text-[color:var(--text-soft)]">{session.id}</div>
                      <div className="mt-2 text-lg font-medium">{session.runs.length} 个运行</div>
                      <div className="mt-1 text-sm text-[color:var(--text-muted)]">
                        {session.requests} 请求 · {session.branches} 分支 · {session.userIds.join(", ")}
                      </div>
                    </div>
                    <Badge tone={evidenceTone(session.evidenceLevel)}>{session.evidenceLevel}</Badge>
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
          <Card eyebrow="当前会话" title={selectedSession.id} strong>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="tech-highlight rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">证据等级</div>
                <div className="mt-3 text-2xl font-semibold">{selectedSession.evidenceLevel}</div>
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

          <Card eyebrow="运行工作区" title="Run 选择与详情">
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
                          <div className="mono text-xs text-[color:var(--text-soft)]">{run.id}</div>
                          <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                            {run.requestCount} req · {run.branchCount} 分支 · {run.avgLatency}
                          </div>
                        </div>
                        <div className="flex flex-col items-end gap-2">
                          <Badge tone={evidenceTone(run.evidenceLevel)}>{run.evidenceLevel}</Badge>
                          <Badge tone={outcomeTone(run.outcome)}>{outcomeLabel(run.outcome)}</Badge>
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
                      <div className="mt-2 text-2xl font-semibold">{selectedRun.id}</div>
                    </div>
                    <div className="flex flex-wrap justify-end gap-2">
                      <Badge tone={evidenceTone(selectedRun.evidenceLevel)}>{selectedRun.evidenceLevel}</Badge>
                      <Badge tone={outcomeTone(selectedRun.outcome)}>{outcomeLabel(selectedRun.outcome)}</Badge>
                    </div>
                  </div>
                  <div className="mt-5 grid gap-3 md:grid-cols-2">
                    <div className="rounded-2xl bg-white/70 p-4">
                      <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">请求闭环</div>
                      <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                        成功 {selectedRun.successCount} · 失败 {selectedRun.failureCount} · Open {selectedRun.openCount}
                      </div>
                    </div>
                    <div className="rounded-2xl bg-white/70 p-4">
                      <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">结构保真</div>
                      <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                        Declared 比例 {Math.round(selectedRun.declaredRatio * 100)}% · Artifacts {selectedRun.artifactCount}
                      </div>
                    </div>
                  </div>
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
        </div>
      ) : null}
    </div>
  );
}
