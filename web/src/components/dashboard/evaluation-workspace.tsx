"use client";

import { useDeferredValue, useMemo, useState } from "react";
import type { EvalSuite, Scorecard } from "@/lib/types";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

type EvaluationWorkspaceProps = {
  evalSuites: EvalSuite[];
  scorecards: Scorecard[];
};

type ScorecardView = "all" | "pass" | "attention";

const SUITE_COPY: Record<string, string> = {
  "slice.aiops.incident_triage":
    "这个 suite 评估模型是否能在 checkout-api 5xx 会话里，沿着 metrics -> logs -> rollout 的证据链完成正确初判。",
  "slice.aiops.rollback_guard":
    "这个 suite 评估模型是否只在证据充分时给出回滚建议，并把缺少 approval 的样本自动留给人工。"
};

export function EvaluationWorkspace({ evalSuites, scorecards }: EvaluationWorkspaceProps) {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<ScorecardView>("all");
  const [selectedSuiteId, setSelectedSuiteId] = useState(evalSuites[0]?.id ?? "");
  const [selectedScorecardId, setSelectedScorecardId] = useState(scorecards[0]?.id ?? "");
  const deferredQuery = useDeferredValue(query);
  const normalizedQuery = deferredQuery.trim().toLowerCase();

  const filteredSuites = useMemo(
    () =>
      evalSuites.filter((suite) => {
        if (!normalizedQuery) {
          return true;
        }

        return [suite.id, suite.sliceId, suite.kind, suite.cohortId]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      }),
    [evalSuites, normalizedQuery]
  );

  const currentSuite =
    filteredSuites.find((suite) => suite.id === selectedSuiteId) ??
    evalSuites.find((suite) => suite.id === selectedSuiteId) ??
    filteredSuites[0] ??
    evalSuites[0];

  const suiteScorecards = useMemo(() => {
    if (!currentSuite) {
      return [];
    }

    return scorecards.filter((scorecard) => {
      if (scorecard.evalSuiteId !== currentSuite.id) {
        return false;
      }

      const matchesView =
        view === "all" ? true : view === "pass" ? scorecard.verdict === "pass" : scorecard.verdict !== "pass";

      if (!matchesView) {
        return false;
      }

      if (!normalizedQuery) {
        return true;
      }

      return [
        scorecard.id,
        scorecard.candidateModel,
        scorecard.baselineModel,
        scorecard.sliceId,
        scorecard.verdict
      ]
        .join(" ")
        .toLowerCase()
        .includes(normalizedQuery);
    });
  }, [currentSuite, normalizedQuery, scorecards, view]);

  const selectedScorecard =
    suiteScorecards.find((scorecard) => scorecard.id === selectedScorecardId) ??
    scorecards.find((scorecard) => scorecard.id === selectedScorecardId) ??
    suiteScorecards[0] ??
    scorecards[0];

  return (
    <div className="grid gap-6 xl:grid-cols-[0.86fr_1.14fr]">
      <Card
        action={<span className="text-xs text-[color:var(--text-soft)]">共 {filteredSuites.length} 个 Suite</span>}
        eyebrow="评测套件"
        title="Suite 选择器"
        strong
      >
        <div className="space-y-4">
          <div className="rounded-[1.1rem] border border-slate-200 bg-white/85 px-4 py-3 shadow-sm">
            <input
              className="w-full bg-transparent text-sm text-[color:var(--text)] outline-none placeholder:text-[color:var(--text-soft)]"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="按 suite / slice / model 搜索"
              value={query}
            />
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              ["all", "全部评分卡"],
              ["pass", "仅通过"],
              ["attention", "待关注"]
            ].map(([id, label]) => (
              <button
                className={
                  view === id
                    ? "rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs text-sky-700"
                    : "rounded-full border border-slate-200 bg-white/85 px-3 py-1.5 text-xs text-[color:var(--text-muted)] hover:bg-sky-50"
                }
                key={id}
                onClick={() => setView(id as ScorecardView)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>

          <div className="space-y-3">
            {filteredSuites.map((suite) => {
              const suiteCards = scorecards.filter((scorecard) => scorecard.evalSuiteId === suite.id);
              const passCount = suiteCards.filter((scorecard) => scorecard.verdict === "pass").length;
              const active = suite.id === currentSuite?.id;

              return (
                <button
                  className={
                    active
                      ? "tech-highlight block w-full rounded-[1.2rem] p-4 text-left"
                      : "panel-soft block w-full rounded-[1.2rem] p-4 text-left transition hover:-translate-y-[1px]"
                  }
                  key={suite.id}
                  onClick={() => {
                    setSelectedSuiteId(suite.id);
                    setSelectedScorecardId(
                      scorecards.find((scorecard) => scorecard.evalSuiteId === suite.id)?.id ?? ""
                    );
                  }}
                  type="button"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="mono text-xs text-[color:var(--text-soft)]">{suite.id}</div>
                      <div className="mt-2 text-lg font-medium">{suite.sliceId}</div>
                      <div className="mt-1 text-sm text-[color:var(--text-muted)]">
                        {suite.kind} · {suite.items} 项 · 通过 {passCount}/{suiteCards.length}
                      </div>
                    </div>
                    <Badge tone={genericStatusTone(suite.status)}>{genericStatusLabel(suite.status)}</Badge>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      {currentSuite ? (
        <div className="space-y-6">
          <Card eyebrow="当前 Suite" title={currentSuite.id} strong>
            <div className="grid gap-3 md:grid-cols-4">
              <div className="tech-highlight rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">Slice</div>
                <div className="mt-3 text-xl font-semibold">{currentSuite.sliceId}</div>
              </div>
              <div className="panel-soft rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">类型</div>
                <div className="mt-3 text-xl font-semibold">{currentSuite.kind}</div>
              </div>
              <div className="panel-soft rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">样本数</div>
                <div className="mt-3 text-xl font-semibold">{currentSuite.items}</div>
              </div>
              <div className="panel-soft rounded-2xl p-4">
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">来源 Cohort</div>
                <div className="mt-3 text-xl font-semibold">{currentSuite.cohortId}</div>
              </div>
            </div>
            <div className="mt-4 rounded-2xl bg-white/70 px-4 py-3 text-sm text-[color:var(--text-muted)]">
              {SUITE_COPY[currentSuite.sliceId] ?? "当前 suite 用于验证这个 slice 是否具备稳定替代价值。"}
            </div>
            <div className="mt-5 flex flex-wrap gap-3">
              <Button href={`/evaluation/${currentSuite.id}`} variant="primary">打开 Suite 详情</Button>
              <Button href="/coverage" variant="secondary">进入覆盖策略</Button>
            </div>
          </Card>

          <Card eyebrow="评分卡抽屉" title="Candidate / Baseline 对比">
            <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
              <div className="space-y-3">
                {suiteScorecards.length ? (
                  suiteScorecards.map((scorecard) => {
                    const active = scorecard.id === selectedScorecard?.id;
                    return (
                      <button
                        className={
                          active
                            ? "tech-highlight block w-full rounded-[1.15rem] p-4 text-left"
                            : "panel-soft block w-full rounded-[1.15rem] p-4 text-left transition hover:-translate-y-[1px]"
                        }
                        key={scorecard.id}
                        onClick={() => setSelectedScorecardId(scorecard.id)}
                        type="button"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="mono text-xs text-[color:var(--text-soft)]">{scorecard.id}</div>
                            <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                              {scorecard.candidateModel} vs {scorecard.baselineModel}
                            </div>
                          </div>
                          <Badge tone={genericStatusTone(scorecard.verdict)}>{genericStatusLabel(scorecard.verdict)}</Badge>
                        </div>
                        <div className="mt-3 text-xs text-[color:var(--text-soft)]">
                          成功率 {scorecard.successRate} · Verifier {scorecard.verifierRate} · Fallback {scorecard.fallbackRate}
                        </div>
                      </button>
                    );
                  })
                ) : (
                  <div className="panel-soft rounded-[1.15rem] p-4 text-sm text-[color:var(--text-muted)]">
                    当前筛选条件下没有评分卡。调整筛选后可继续查看 verdict 细节。
                  </div>
                )}
              </div>

              {selectedScorecard ? (
                <div className="tech-highlight rounded-[1.25rem] p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">当前评分卡</div>
                      <div className="mt-2 text-2xl font-semibold">{selectedScorecard.id}</div>
                    </div>
                    <Badge tone={genericStatusTone(selectedScorecard.verdict)}>
                      {genericStatusLabel(selectedScorecard.verdict)}
                    </Badge>
                  </div>
                  <div className="mt-5 grid gap-3 md:grid-cols-2">
                    <div className="rounded-2xl bg-white/70 p-4">
                      <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">模型对比</div>
                      <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                        {selectedScorecard.candidateModel} 对比 {selectedScorecard.baselineModel}
                      </div>
                    </div>
                    <div className="rounded-2xl bg-white/70 p-4">
                      <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">质量结论</div>
                      <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                        成功率 {selectedScorecard.successRate} · Verifier {selectedScorecard.verifierRate}
                      </div>
                    </div>
                    <div className="rounded-2xl bg-white/70 p-4">
                      <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">性能与成本</div>
                      <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                        P95 {selectedScorecard.p95Latency} · 成本 {selectedScorecard.cost}
                      </div>
                    </div>
                    <div className="rounded-2xl bg-white/70 p-4">
                      <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">回退信号</div>
                      <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                        Fallback {selectedScorecard.fallbackRate} · Slice {selectedScorecard.sliceId}
                      </div>
                    </div>
                  </div>
                  <div className="mt-5 flex flex-wrap gap-3">
                    <Button href={`/evaluation/${selectedScorecard.evalSuiteId}`} variant="primary">进入 Suite 详情</Button>
                    <Button href="/flows/validate-slice" variant="secondary">继续验证流程</Button>
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
