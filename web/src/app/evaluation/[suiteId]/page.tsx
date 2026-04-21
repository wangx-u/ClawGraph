import type { StatusTone } from "@/lib/types";
import { getDashboardBundle } from "@/lib/data-source";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";

type SuiteRecommendation = {
  badge: string;
  tone: StatusTone;
  title: string;
  summary: string;
  nextAction: string;
  reasons: string[];
};

function buildSuiteRecommendation({
  failedCount,
  holdCount,
  scorecardCount,
  suiteStatus,
  thresholdCount
}: {
  failedCount: number;
  holdCount: number;
  scorecardCount: number;
  suiteStatus: string;
  thresholdCount: number;
}): SuiteRecommendation {
  if (!scorecardCount) {
    return {
      badge: "待补评分卡",
      tone: "accent",
      title: "当前还不能进入上线评审",
      summary: "这套评测还没有产出可判断的评分卡，无法形成 go / no-go 结论。",
      nextAction: "先补齐固定评测执行和评分卡，再继续判断这条替代链路是否值得进入上线控制面。",
      reasons: ["尚未产出评分卡", thresholdCount ? `已绑定 ${thresholdCount} 条上线门槛` : "还没有绑定稳定的上线门槛"]
    };
  }

  if (failedCount > 0 || suiteStatus === "failed") {
    return {
      badge: "返回闭环",
      tone: "danger",
      title: "建议回到数据或模型闭环",
      summary: `${failedCount} 张评分卡未通过当前门槛，当前不应进入上线评审。`,
      nextAction: "优先处理失败项、补样本或重新训练，再回到这套评测验证是否改善。",
      reasons: [`未通过评分卡 ${failedCount} 张`, thresholdCount ? `当前绑定 ${thresholdCount} 条上线门槛` : "当前门槛仍待补齐"]
    };
  }

  if (holdCount > 0 || suiteStatus === "review" || !thresholdCount) {
    return {
      badge: "继续观察",
      tone: "warning",
      title: "建议继续观察，不直接进入上线评审",
      summary: holdCount
        ? `${holdCount} 张评分卡仍处于观察态，当前结论还没有稳定收口。`
        : "当前评测结果没有明显失败，但上线门槛或决策策略还不够完整。",
      nextAction: "继续补样本、等待下一轮评分卡，或先补齐稳定门槛后再决定是否进入上线控制面。",
      reasons: [
        holdCount ? `观察态评分卡 ${holdCount} 张` : "当前没有评分卡失败项",
        thresholdCount ? `已绑定 ${thresholdCount} 条上线门槛` : "还没有绑定稳定的上线门槛"
      ]
    };
  }

  return {
    badge: "可进入上线评审",
    tone: "success",
    title: "建议进入上线控制面",
    summary: `${scorecardCount} 张评分卡当前都通过，且评测套件已经具备稳定门槛。`,
    nextAction: "带着当前评分卡、门槛和时间范围进入上线控制面，确认放量范围、审批与回滚监控。",
    reasons: [`通过评分卡 ${scorecardCount} 张`, `已绑定 ${thresholdCount} 条上线门槛`]
  };
}

export default async function EvalSuiteDetailPage({
  params
}: {
  params: Promise<{ suiteId: string }>;
}) {
  const { suiteId } = await params;
  const {
    bundle: { evalSuites, scorecards }
  } = await getDashboardBundle();
  const suite = evalSuites.find((item) => item.id === suiteId) ?? evalSuites[0];
  const suiteScorecards = suite
    ? scorecards.filter((scorecard) => scorecard.evalSuiteId === suite.id)
    : [];
  const thresholdItems = suite?.launchThresholds ?? [];
  const failedScorecards = suiteScorecards.filter((scorecard) => scorecard.verdict === "fail");
  const holdScorecards = suiteScorecards.filter((scorecard) => scorecard.verdict === "hold");
  const recommendation = buildSuiteRecommendation({
    failedCount: suiteScorecards.filter((scorecard) => scorecard.verdict === "fail").length,
    holdCount: holdScorecards.length,
    scorecardCount: suiteScorecards.length,
    suiteStatus: suite?.status ?? "pending",
    thresholdCount: thresholdItems.length
  });
  const tabItems = [
    {
      id: "metrics",
      label: "指标",
      content: (
        <div className="grid gap-3 md:grid-cols-2">
          {suiteScorecards.map((scorecard) => (
            <div className="panel-soft rounded-[1.1rem] p-4" key={scorecard.id}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="mt-2 text-lg font-medium">
                    {scorecard.candidateModel} vs {scorecard.baselineModel}
                  </div>
                </div>
                <Badge tone={genericStatusTone(scorecard.verdict)}>{genericStatusLabel(scorecard.verdict)}</Badge>
              </div>
              <div className="mt-4 space-y-2 text-sm text-[color:var(--text-muted)]">
                <div>任务：{scorecard.sliceLabel ?? scorecard.sliceId}</div>
                <div>成功率：{scorecard.successRate}</div>
                <div>Verifier：{scorecard.verifierRate}</div>
                <div>P95 延迟：{scorecard.p95Latency}</div>
                <div>Fallback：{scorecard.fallbackRate}</div>
              </div>
              <details className="mt-4 panel-soft rounded-2xl p-4">
                <summary className="cursor-pointer text-sm font-medium text-[color:var(--text)]">查看技术明细</summary>
                <div className="mono mt-3 text-xs text-[color:var(--text-soft)]">{scorecard.id}</div>
              </details>
            </div>
          ))}
        </div>
      )
    },
    {
      id: "thresholds",
      label: "上线门槛",
      content: (
        <div className="space-y-4">
          <div className="tech-highlight rounded-2xl p-4 text-sm leading-6 text-[color:var(--text-muted)]">
            {suite?.decisionPolicySummary ?? "当前还没有绑定稳定的上线门槛，请先在评测套件上补齐决策策略。"}
          </div>
          {thresholdItems.length ? thresholdItems.map((item) => (
            <div className="panel-soft rounded-2xl p-4" key={item.label}>
              <div className="font-medium">{item.label}</div>
              <div className="mt-2 text-sm text-[color:var(--text)]">{item.target}</div>
              <div className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">{item.reason}</div>
            </div>
          )) : (
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
              当前还没有可执行的上线门槛。
            </div>
          )}
        </div>
      )
    },
    {
      id: "history",
      label: "决策历史",
      content: (
        <div className="grid gap-3 md:grid-cols-2">
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            来源批次：{suite.cohortName ?? suite.cohortId}
          </div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            当前状态：{genericStatusLabel(suite.status)}
          </div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            最新 verdict：{suite.latestVerdict ? genericStatusLabel(suite.latestVerdict) : "待补充"}
          </div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            时间范围：{suite.timeRangeLabel ?? "待补充"}
          </div>
        </div>
      )
    },
    {
      id: "failures",
      label: "待关注项",
      content: (
        <div className="space-y-3">
          {failedScorecards.length ? failedScorecards.map((scorecard) => (
            <div className="panel-soft rounded-2xl p-4" key={scorecard.id}>
              <div className="font-medium">{scorecard.candidateModel} 未通过当前门槛</div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                Verifier {scorecard.verifierRate} · Fallback {scorecard.fallbackRate} · P95 {scorecard.p95Latency}
              </div>
            </div>
          )) : null}
          {holdScorecards.length ? holdScorecards.map((scorecard) => (
            <div className="panel-soft rounded-2xl p-4" key={scorecard.id}>
              <div className="font-medium">{scorecard.candidateModel} 仍在观察，不直接进入上线评审</div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                Verifier {scorecard.verifierRate} · Fallback {scorecard.fallbackRate} · P95 {scorecard.p95Latency}
              </div>
            </div>
          )) : null}
          {!failedScorecards.length && !holdScorecards.length ? (
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
              当前没有失败或观察中的评分卡，主要关注通过项的持续稳定性即可。
            </div>
          ) : null}
        </div>
      )
    }
  ];

  if (!suite) {
    return (
      <EmptyState
        actionHref="/evaluation"
        actionLabel="返回评测"
        description="当前还没有可查看的评测套件。先从 evaluation 页面创建一套。"
        title="评测套件不存在"
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={suite.title ?? suite.name ?? `评测套件 ${suite.id}`}
        description="从套件结构、candidate 指标和最新 recommendation 视角查看一个 slice 的替代决策依据。"
        primaryAction={<Button href="/coverage" variant="primary">进入上线控制面</Button>}
        secondaryAction={<Button href="/evaluation" variant="secondary">返回评测</Button>}
      />

      <Card eyebrow="套件摘要" title={suite.kind} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">任务切片</div><div className="mt-3 text-xl font-semibold">{suite.sliceLabel ?? suite.sliceId}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">类型</div><div className="mt-3 text-xl font-semibold">{suite.kind}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">样本数</div><div className="mt-3 text-xl font-semibold">{suite.items}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">来源批次</div><div className="mt-3 text-xl font-semibold">{suite.cohortName ?? suite.cohortId}</div></div>
        </div>
        <div className="mt-4 rounded-2xl bg-white/70 px-4 py-3 text-sm text-[color:var(--text-muted)]">
          {suite.timeRangeLabel ?? "时间范围待补充"} · 当前状态 {genericStatusLabel(suite.status)}
        </div>
        <div className="mt-4 tech-highlight rounded-[1.2rem] p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">综合结论</div>
              <div className="mt-2 text-xl font-semibold">{recommendation.title}</div>
            </div>
            <Badge tone={recommendation.tone}>{recommendation.badge}</Badge>
          </div>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-[color:var(--text-muted)]">
            {recommendation.summary}
          </p>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {recommendation.reasons.map((reason) => (
              <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={reason}>
                {reason}
              </div>
            ))}
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
              下一步：{recommendation.nextAction}
            </div>
          </div>
        </div>
      </Card>

      <Card eyebrow="决策面板" title="最新推荐">
        <Tabs active="metrics" items={tabItems} />
      </Card>
    </div>
  );
}
