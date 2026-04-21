import { getDashboardBundle } from "@/lib/data-source";
import { evaluateLaunchReadiness, isResolvedNonLaunchDecision } from "@/lib/launch-control";
import {
  relatedCandidatesForRequest,
  relatedExecutionsForRequest,
  relatedHandoffsForRequest
} from "@/lib/training-registry";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import type { DashboardBundle, EvalExecution, ModelCandidate, RouterHandoff, TrainingRequest } from "@/lib/types";
import {
  createTrainingHandoff,
  evaluateTrainingCandidate,
  submitTrainingRequest
} from "@/app/training/actions";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

type ReplacementChain = {
  request: TrainingRequest;
  candidates: ModelCandidate[];
  executions: EvalExecution[];
  handoffs: RouterHandoff[];
  latestCandidate?: ModelCandidate;
  latestExecution?: EvalExecution;
  latestHandoff?: RouterHandoff;
  stageLabel: string;
  stageTone: "neutral" | "success" | "warning" | "danger" | "info" | "accent";
  nextAction: string;
  needsAttention: boolean;
  launchReady: boolean;
  actionLabel: string;
  handoffSummary: string;
};

function buildReplacementChains(bundle: DashboardBundle): ReplacementChain[] {
  return (bundle.trainingRequests ?? []).map((request) => {
    const candidates = relatedCandidatesForRequest(bundle, request.id);
    const executions = relatedExecutionsForRequest(bundle, request.id);
    const handoffs = relatedHandoffsForRequest(bundle, request.id);
    const latestCandidate = candidates[0];
    const latestExecution = executions[0];
    const latestHandoff = handoffs[0];

    if (latestHandoff) {
      const readiness = evaluateLaunchReadiness(latestHandoff);

      if (readiness.executable) {
        return {
          request,
          candidates,
          executions,
          handoffs,
          latestCandidate,
          latestExecution,
          latestHandoff,
          stageLabel: "可进入上线控制面",
          stageTone: "success",
          nextAction: "这份交接已经满足上线条件，可以进入上线控制面执行首轮 canary。",
          needsAttention: false,
          launchReady: true,
          actionLabel: "进入上线控制面",
          handoffSummary: `${handoffs.length} 份交接包，当前可执行`
        };
      }

      if (latestHandoff.decision === "promote") {
        return {
          request,
          candidates,
          executions,
          handoffs,
          latestCandidate,
          latestExecution,
          latestHandoff,
          stageLabel: "交接待补上线条件",
          stageTone: "warning",
          nextAction: readiness.blockers[0] ?? "先补齐审批、Router Ack 或监控绑定，再进入上线控制面。",
          needsAttention: true,
          launchReady: false,
          actionLabel: "补齐上线条件",
          handoffSummary: `${handoffs.length} 份交接包，仍需补条件`
        };
      }

      if (isResolvedNonLaunchDecision(latestHandoff)) {
        return {
          request,
          candidates,
          executions,
          handoffs,
          latestCandidate,
          latestExecution,
          latestHandoff,
          stageLabel: "已形成保留决策",
          stageTone: "info",
          nextAction: "这条链路当前已明确保持离线或回退，后续只需等待下一轮数据或评测更新。",
          needsAttention: false,
          launchReady: false,
          actionLabel: "查看当前决策",
          handoffSummary: `${handoffs.length} 份交接包，当前已收口为离线决策`
        };
      }

      return {
        request,
        candidates,
        executions,
        handoffs,
        latestCandidate,
        latestExecution,
        latestHandoff,
        stageLabel: "等待交接确认",
        stageTone: "warning",
        nextAction: "交接已经生成，但当前决策还没有稳定收口，先回到评测和放量决策确认下一步。",
        needsAttention: true,
        launchReady: false,
        actionLabel: "继续接替链路",
        handoffSummary: `${handoffs.length} 份交接包，当前仍待确认`
      };
    }

    if (latestExecution) {
      return {
        request,
        candidates,
        executions,
        handoffs,
        latestCandidate,
        latestExecution,
        stageLabel: "等待交接决策",
        stageTone: "info",
        nextAction: "根据 scorecard 和 promotion 结果形成 handoff 或保留决策。",
        needsAttention: true,
        launchReady: false,
        actionLabel: "继续验证链路",
        handoffSummary: "等待 handoff"
      };
    }

    if (latestCandidate) {
      return {
        request,
        candidates,
        executions,
        handoffs,
        latestCandidate,
        latestExecution,
        latestHandoff,
        stageLabel: "等待固定评测",
        stageTone: "accent",
        nextAction: "让候选模型进入冻结评测资产，产出可执行的 scorecard。",
        needsAttention: true,
        launchReady: false,
        actionLabel: "继续验证链路",
        handoffSummary: "等待 handoff"
      };
    }

    return {
      request,
      candidates,
      executions,
      handoffs,
      latestCandidate,
      latestExecution,
      latestHandoff,
      stageLabel: "等待候选产出",
      stageTone: "warning",
      nextAction: "等待训练系统回写 candidate / checkpoint，再进入下游验证。",
      needsAttention: true,
      launchReady: false,
      actionLabel: "继续验证链路",
      handoffSummary: "等待 handoff"
    };
  });
}

function TrainingChainAction({ chain }: { chain: ReplacementChain }) {
  if (!chain.latestCandidate) {
    return (
      <form action={submitTrainingRequest}>
        <input name="requestId" type="hidden" value={chain.request.id} />
        <Button type="submit" variant="primary">提交训练</Button>
      </form>
    );
  }

  if (!chain.latestExecution) {
    return (
      <form action={evaluateTrainingCandidate}>
        <input name="candidateId" type="hidden" value={chain.latestCandidate.id} />
        <input
          name="evalSuiteId"
          type="hidden"
          value={chain.request.evalSuiteId ?? ""}
        />
        <input
          name="baselineModel"
          type="hidden"
          value={chain.latestCandidate.baseModel ?? chain.request.baseModel ?? ""}
        />
        <Button type="submit" variant="primary">发起评测</Button>
      </form>
    );
  }

  if (!chain.latestHandoff && chain.latestExecution.promotionDecisionId) {
    return (
      <form action={createTrainingHandoff}>
        <input name="candidateId" type="hidden" value={chain.latestCandidate.id} />
        <input
          name="promotionDecisionId"
          type="hidden"
          value={chain.latestExecution.promotionDecisionId ?? ""}
        />
        <Button type="submit" variant="primary">生成交接</Button>
      </form>
    );
  }

  return (
    <Button href={`/training/requests/${chain.request.id}`} variant="primary">
      打开当前链路
    </Button>
  );
}

export default async function TrainingPage() {
  const { bundle } = await getDashboardBundle();
  const {
    evalExecutions,
    modelCandidates,
    routerHandoffs,
    trainingRegistrySummary,
    trainingRequests
  } = bundle;

  if (
    !(trainingRequests?.length || 0) &&
    !(modelCandidates?.length || 0) &&
    !(evalExecutions?.length || 0) &&
    !(routerHandoffs?.length || 0)
  ) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="模型接替工作区"
          description="查看外部训练系统回写的训练请求、候选模型、固定评测和交接状态，把模型接替链路放到同一个工作区里。"
          primaryAction={<Button href="/datasets" variant="primary">打开数据集</Button>}
          secondaryAction={<Button href="/evaluation" variant="secondary">打开评测</Button>}
        />
        <EmptyState
          actionHref="/datasets"
          actionLabel="回到数据快照"
          description="当前还没有可追踪的接替资产。先从冻结快照提交训练请求，或把已有训练配置清单同步入库。"
          title="还没有模型接替链路"
        />
      </div>
    );
  }

  const chains = buildReplacementChains(bundle);
  const featuredChain = chains.find((chain) => chain.needsAttention) ?? chains[0];

  return (
    <div className="space-y-6">
      <PageHeader
        title="模型接替工作区"
        description="把训练请求、候选模型、固定评测、放量决策和交接状态串成一条接替链路，先看当前链路卡在哪一步。"
        primaryAction={
          <Button href={featuredChain?.latestHandoff ? "/coverage" : "/evaluation"} variant="primary">
            {featuredChain?.actionLabel ?? "继续验证链路"}
          </Button>
        }
        secondaryAction={<Button href="/datasets" variant="secondary">返回数据快照</Button>}
      />

      {trainingRegistrySummary ? (
        <Card eyebrow="替换注册表" title="当前模型接替概览" strong>
          <div className="grid gap-3 md:grid-cols-4">
            <div className="tech-highlight rounded-2xl p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">已关联请求</div>
              <div className="mt-3 text-2xl font-semibold">
                {trainingRegistrySummary.linkedRequestCount}/{trainingRegistrySummary.requestCount}
              </div>
            </div>
            <div className="panel-soft rounded-2xl p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">已进入固定评测</div>
              <div className="mt-3 text-2xl font-semibold">{trainingRegistrySummary.evaluatedCandidateCount}</div>
            </div>
            <div className="panel-soft rounded-2xl p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">已形成交接包</div>
              <div className="mt-3 text-2xl font-semibold">{trainingRegistrySummary.handedOffCandidateCount}</div>
            </div>
            <div className="panel-soft rounded-2xl p-4">
              <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">最近更新时间</div>
              <div className="mt-3 text-lg font-semibold">{trainingRegistrySummary.lastUpdated ?? "-"}</div>
            </div>
          </div>
        </Card>
      ) : null}

      {featuredChain ? (
        <Card
          action={<TrainingChainAction chain={featuredChain} />}
          eyebrow="当前接替链路"
          title={featuredChain.request.title}
          strong
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={featuredChain.stageTone}>{featuredChain.stageLabel}</Badge>
            <Badge tone={genericStatusTone(featuredChain.request.status)}>
              {genericStatusLabel(featuredChain.request.status)}
            </Badge>
          </div>
          <p className="mt-4 max-w-3xl text-sm leading-6 text-[color:var(--text-muted)]">
            {featuredChain.nextAction}
          </p>
          <div className="mt-4 grid gap-3 xl:grid-cols-5">
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Step 1 请求</div>
              <div className="mt-2 font-medium">{featuredChain.request.recipeName}</div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                {featuredChain.request.datasetSnapshotTitle ?? featuredChain.request.datasetSnapshotId ?? "未绑定快照"}
              </div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Step 2 候选</div>
              <div className="mt-2 font-medium">{featuredChain.latestCandidate?.title ?? "等待训练回写"}</div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                {featuredChain.latestCandidate?.candidateModel ?? `候选 ${featuredChain.candidates.length} 个`}
              </div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Step 3 固定评测</div>
              <div className="mt-2 font-medium">{featuredChain.latestExecution?.title ?? "等待评测执行"}</div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                {featuredChain.latestExecution?.metricsSummary ?? `评测 ${featuredChain.executions.length} 个`}
              </div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Step 4 决策</div>
              <div className="mt-2 font-medium">
                {featuredChain.latestExecution?.promotionDecision
                  ? genericStatusLabel(featuredChain.latestExecution.promotionDecision)
                  : featuredChain.latestHandoff
                    ? genericStatusLabel(featuredChain.latestHandoff.decision)
                    : "等待决策"}
              </div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                {featuredChain.latestExecution?.promotionStage ?? featuredChain.latestHandoff?.stage ?? "待补充"}
              </div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Step 5 交接</div>
              <div className="mt-2 font-medium">{featuredChain.latestHandoff?.title ?? "等待 handoff"}</div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                {featuredChain.latestHandoff
                  ? featuredChain.handoffSummary
                  : "进入 coverage 后确认切流与回滚"}
              </div>
            </div>
          </div>
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Card eyebrow="链路清单" title="所有模型接替链路" strong>
          <div className="space-y-3">
            {chains.map((chain) => (
              <div className="panel-soft rounded-[1.15rem] p-4" key={chain.request.id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-medium">{chain.request.title}</div>
                    <div className="mt-2 text-sm text-[color:var(--text-muted)]">{chain.request.summary}</div>
                    <div className="mt-3 text-sm text-[color:var(--text-muted)]">
                      快照：{chain.request.datasetSnapshotTitle ?? chain.request.datasetSnapshotId ?? "未绑定"} · 候选 {chain.candidates.length} · 评测 {chain.executions.length} · 交接 {chain.handoffs.length}
                    </div>
                    <div className="mt-2 text-sm text-[color:var(--text-muted)]">下一步：{chain.nextAction}</div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <Badge tone={chain.stageTone}>{chain.stageLabel}</Badge>
                    <div className="flex flex-wrap justify-end gap-2">
                      <TrainingChainAction chain={chain} />
                      <Button href={`/training/requests/${chain.request.id}`} variant="ghost">详情</Button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card eyebrow="决策入口" title="当前最常见的下一步">
          <div className="space-y-3">
            {[
              {
                title: "训练已回写但未固定评测",
                detail: "候选模型已经出现时，优先把它送进冻结评测资产，避免只看训练日志做决策。"
              },
              {
                title: "评测已完成但未形成 handoff",
                detail: "scorecard 已经出来后，应明确保留、放量或回退，而不是让结果停留在对比页面。"
              },
              {
                title: "交接包已就绪时转入上线控制面",
                detail: "交接包完成后，应立刻确认覆盖范围、审批人和 rollback 监控，而不是继续停留在训练页。"
              }
            ].map((item) => (
              <div className="panel-soft rounded-[1.1rem] p-4" key={item.title}>
                <div className="font-medium">{item.title}</div>
                <p className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">{item.detail}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
