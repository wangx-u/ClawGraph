import { getDashboardBundle } from "@/lib/data-source";
import { reviewStatusLabel, reviewStatusTone, workflowStageLabel, workflowStageTone } from "@/lib/presenters";
import type { Artifact, SessionSummary, StatusTone, WorkflowRun } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";

type JudgeDecision = {
  sessionId: string;
  runId: string;
  title: string;
  summary: string;
  decision: string;
  stageLabel: string;
  stageTone: StatusTone;
  reviewLabel: string;
  reviewTone: StatusTone;
  reasons: string[];
  nextAction: string;
  builders: string[];
};

function buildJudgeDecisionQueue(sessions: SessionSummary[], workflowRuns?: WorkflowRun[]): JudgeDecision[] {
  if (workflowRuns?.length) {
    return workflowRuns
      .filter((run) => run.stage === "annotate" || run.stage === "augment" || run.stage === "review")
      .map((run) => ({
        sessionId: run.sessionId,
        runId: run.runId,
        title: run.title ?? run.stageLabel,
        summary: run.summary ?? run.stageDetail,
        decision:
          run.stage === "annotate"
            ? "先补基础标签"
            : run.stage === "augment"
              ? "补关键语义后再继续"
              : "送人工复核",
        stageLabel: run.stageLabel,
        stageTone: workflowStageTone(run.stage),
        reviewLabel: reviewStatusLabel(run.reviewStatus),
        reviewTone: reviewStatusTone(run.reviewStatus),
        reasons: run.reviewReasons.length ? run.reviewReasons : run.blockers,
        nextAction: run.nextAction,
        builders: run.readyBuilders
      }));
  }

  return sessions
    .flatMap((session) =>
      session.runs.map((run) => {
        const reasons = [
          ...(run.openCount > 0 ? [`${run.openCount} 个 open span 仍未闭合`] : []),
          ...(run.evidenceLevel === "E0" ? ["任务实例键和关键标签仍不稳定"] : []),
          ...(run.evidenceLevel === "E1" ? ["关键决策语义尚未补齐，仍不能直接冻结"] : []),
          ...session.anomalies.filter((item) => item.includes(run.id)).slice(0, 2)
        ];
        const stage =
          run.openCount > 0 ? "annotate" : run.evidenceLevel === "E0" ? "annotate" : run.evidenceLevel === "E1" ? "augment" : "review";
        const reviewTone: StatusTone = stage === "review" ? "accent" : "warning";

        return {
          sessionId: session.id,
          runId: run.id,
          title: run.title ?? run.id,
          summary: run.summary ?? "当前根据运行结果和证据等级推断下一步判断动作。",
          decision:
            stage === "annotate"
              ? "先补基础标签"
              : stage === "augment"
                ? "补关键语义后再继续"
                : "可复查后进入数据池",
          stageLabel: workflowStageLabel(stage),
          stageTone: workflowStageTone(stage),
          reviewLabel: stage === "review" ? "准备复查" : "自动处理中",
          reviewTone,
          reasons: reasons.length ? reasons : ["当前没有额外阻塞，可继续复查 builder readiness。"],
          nextAction:
            stage === "review"
              ? "确认 builder 匹配和最后的人工抽检。"
              : "回到回放页补齐结构、标签或关键决策语义。",
          builders: run.readyBuilders ?? []
        };
      })
    )
    .sort((left, right) => left.reasons.length - right.reasons.length)
    .reverse();
}

function artifactTypeLabel(type: string) {
  switch (type) {
    case "annotation":
      return "标签与事件判断";
    case "score":
      return "质量评分";
    case "preference":
      return "偏好判断";
    default:
      return type;
  }
}

function artifactScopeLabel(artifact: Artifact) {
  if (artifact.targetRef.startsWith("run:")) {
    return "运行级";
  }
  if (artifact.targetRef.startsWith("branch:")) {
    return "分支级";
  }
  if (artifact.targetRef.startsWith("fact:")) {
    return "步骤级";
  }
  return "其他";
}

export default async function SupervisionPage() {
  const {
    bundle: { artifacts, sessions, workflowRuns }
  } = await getDashboardBundle();
  const latestSession = sessions[0];
  const latestRun = latestSession?.runs[0];
  const latestReplayHref =
    latestSession && latestRun
      ? `/sessions/${latestSession.id}/runs/${latestRun.id}/replay`
      : "/sessions";
  const judgeQueue = buildJudgeDecisionQueue(sessions, workflowRuns);
  const annotateCount = judgeQueue.filter((item) => item.decision === "先补基础标签").length;
  const augmentCount = judgeQueue.filter((item) => item.decision === "补关键语义后再继续").length;
  const reviewCount = judgeQueue.filter((item) => item.decision === "送人工复核").length;
  const readyCount = judgeQueue.filter((item) => item.decision === "可复查后进入数据池").length;
  const artifactSummary = [
    {
      label: "标签与事件判断",
      count: artifacts.filter((artifact) => artifact.type === "annotation").length,
      detail: "用于稳定任务实例、动作结果和关键事件的归因。"
    },
    {
      label: "质量评分",
      count: artifacts.filter((artifact) => artifact.type === "score").length,
      detail: "用于判断样本质量和是否需要降级到人工复查。"
    },
    {
      label: "偏好判断",
      count: artifacts.filter((artifact) => artifact.type === "preference").length,
      detail: "用于保留更优路径，为偏好学习和 RL 提供素材。"
    }
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="自动判断工作区"
        description="先看系统给出的自动结论、原因和下一步动作，只有真正不确定的运行再送人工复核，而不是先翻 artifact 技术字段。"
        primaryAction={<Button href="/flows/build-dataset" variant="primary">继续数据集流程</Button>}
        secondaryAction={<Button href={latestReplayHref} variant="secondary">返回最近回放</Button>}
      />

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
        <div className="surface-strong rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">待补基础标签</div>
          <div className="mt-3 text-3xl font-semibold">{annotateCount}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">待补关键语义</div>
          <div className="mt-3 text-3xl font-semibold">{augmentCount}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">待人工复核</div>
          <div className="mt-3 text-3xl font-semibold">{reviewCount}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">接近数据池准入</div>
          <div className="mt-3 text-3xl font-semibold">{readyCount}</div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <Card eyebrow="自动结论" title="先处理这些判断结果" strong>
          <div className="space-y-3">
            {judgeQueue.length ? (
              judgeQueue.slice(0, 4).map((item) => (
                <div className="panel-soft rounded-[1.15rem] p-4" key={item.runId}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="text-xs text-[color:var(--text-soft)]">运行 {item.runId}</div>
                      <div className="mt-2 text-base font-medium">{item.title}</div>
                      <p className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">{item.summary}</p>
                    </div>
                    <div className="flex flex-wrap justify-end gap-2">
                      <Badge tone={item.stageTone}>{item.stageLabel}</Badge>
                      <Badge tone={item.reviewTone}>{item.reviewLabel}</Badge>
                    </div>
                  </div>
                  <div className="tech-highlight mt-4 rounded-[1.05rem] p-4">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">自动建议</div>
                    <div className="mt-2 text-base font-medium">{item.decision}</div>
                    <div className="mt-2 text-sm text-[color:var(--text-muted)]">下一步：{item.nextAction}</div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {item.reasons.slice(0, 3).map((reason) => (
                      <Badge key={reason} tone="warning">
                        {reason}
                      </Badge>
                    ))}
                    {item.builders.map((builder) => (
                      <Badge key={`${item.runId}-${builder}`} tone="accent">
                        Builder {builder}
                      </Badge>
                    ))}
                  </div>
                  <div className="mt-4">
                    <Button href={`/sessions/${item.sessionId}/runs/${item.runId}/replay`} variant="secondary">
                      打开回放确认
                    </Button>
                  </div>
                </div>
              ))
            ) : (
              <div className="panel-soft rounded-[1.15rem] p-4 text-sm text-[color:var(--text-muted)]">
                当前没有积压的自动判断任务。新采集的运行会在这里先形成结论，再决定是否进入复核。
              </div>
            )}
          </div>
        </Card>

        <Card eyebrow="判断规则" title="系统是按什么口径给结论的">
          <div className="space-y-3">
            {[
              {
                title: "先闭合，再判断",
                detail: "只要仍有 open span，系统就优先要求补齐终态，而不是继续产出下游数据。"
              },
              {
                title: "先稳定任务身份",
                detail: "task instance、模板和来源不稳时，优先补标签，避免同类样本被切成多个批次。"
              },
              {
                title: "关键决策语义要补齐",
                detail: "retry、fallback、route、task_completed 等语义齐全后，才适合进入可筛选或可导出的状态。"
              },
              {
                title: "不确定再送人工",
                detail: "系统会优先给出自动建议，只有分歧、高风险或低置信样本才进入人工复核。"
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

      <Card eyebrow="判断产物" title="自动判断已经写入的可追溯证据">
        <div className="mb-4 grid gap-3 md:grid-cols-3">
          {artifactSummary.map((item) => (
            <div className="panel-soft rounded-[1.1rem] p-4" key={item.label}>
              <div className="text-xs tracking-[0.16em] text-[color:var(--text-soft)]">{item.label}</div>
              <div className="mt-3 text-2xl font-semibold">{item.count}</div>
              <div className="mt-2 text-xs leading-5 text-[color:var(--text-muted)]">{item.detail}</div>
            </div>
          ))}
        </div>
        <DataTable
          headers={["判断类型", "适用对象", "置信度", "状态", "版本 / 技术明细"]}
          rows={artifacts.map((artifact) => [
            <div key={`${artifact.id}-type`}>
              <div className="font-medium">{artifactTypeLabel(artifact.type)}</div>
              <div className="mt-1 text-sm text-[color:var(--text-muted)]">由 {artifact.producer} 写入</div>
            </div>,
            <div key={`${artifact.id}-scope`}>
              <div>{artifactScopeLabel(artifact)}</div>
              <div className="mt-1 text-sm text-[color:var(--text-muted)]">{artifact.targetRef}</div>
            </div>,
            artifact.confidence,
            <Badge key={`${artifact.id}-status`} tone="info">
              {artifact.status === "active" ? "已生效" : artifact.status}
            </Badge>,
            <div key={`${artifact.id}-version`}>
              <div>{artifact.version}</div>
              <div className="mono mt-1 text-xs text-[color:var(--text-soft)]">{artifact.id}</div>
            </div>
          ])}
        />
      </Card>
    </div>
  );
}
