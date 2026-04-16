import { getDashboardBundle } from "@/lib/data-source";
import {
  evidenceLabel,
  genericStatusLabel,
  genericStatusTone,
  outcomeLabel,
  outcomeTone,
  requestActorLabel,
  shortId,
  workflowStageTone
} from "@/lib/presenters";
import type { ReplayStep } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";

export default async function ReplayPage({
  params
}: {
  params: Promise<{ sessionId: string; runId: string }>;
}) {
  const { sessionId, runId } = await params;
  const {
    bundle: { replayRecords, sessions }
  } = await getDashboardBundle();
  const replay = replayRecords.find((item) => item.sessionId === sessionId && item.runId === runId) ?? replayRecords[0] ?? null;
  const session = replay ? sessions.find((item) => item.id === replay.sessionId) ?? sessions[0] ?? null : null;
  const run = replay && session ? session.runs.find((item) => item.id === replay.runId) ?? session.runs[0] ?? null : null;

  if (!replay || !session || !run) {
    return (
      <EmptyState
        actionHref="/sessions"
        actionLabel="返回会话收件箱"
        description="当前没有可回放的运行数据，先确认 session 是否已采集并写入 store。"
        title="回放数据不存在"
      />
    );
  }

  const artifactCount = run.artifactCount ?? replay.requests.reduce((sum, item) => sum + item.artifactCount, 0);
  const builderBadges = run.readyBuilders ?? [];
  const runBlockers = run.readinessBlockers ?? run.blockers ?? [];
  const timelineSteps: ReplayStep[] =
    replay.timelineSteps ?? replay.timeline.map((label) => ({ label }));

  return (
    <div className="space-y-6">
      <PageHeader
        title={replay.title ? `回放 ${replay.title}` : `回放 ${shortId(replay.runId)}`}
        description="按执行顺序还原一个真实运行的请求、分支和语义事件，用于判断它现在卡在哪一步，以及下一步要补什么。"
        primaryAction={<Button href={`/sessions/${session.id}`} variant="primary">返回会话</Button>}
        secondaryAction={<Button href="/supervision" variant="secondary">进入数据准备</Button>}
      />

      <Card eyebrow="回放摘要" title={replay.title ?? run.title ?? shortId(replay.runId)} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">结果</div><div className="mt-3 text-2xl font-semibold">{outcomeLabel(run.outcome)}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">请求数</div><div className="mt-3 text-2xl font-semibold">{replay.requests.length}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">分支数</div><div className="mt-3 text-2xl font-semibold">{replay.branches.length}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">判断记录</div><div className="mt-3 text-2xl font-semibold">{artifactCount}</div></div>
        </div>
        <div className="mt-4 text-sm text-[color:var(--text-muted)]">
          {replay.summary ?? run.summary ?? "这次回放展示了一次完整运行的主要步骤、分支和后续动作。"}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge tone={outcomeTone(run.outcome)}>{outcomeLabel(run.outcome)}</Badge>
          <Badge tone="info">{run.avgLatency}</Badge>
          <Badge tone={workflowStageTone(run.stage)}>{run.stageLabel ?? evidenceLabel(run.evidenceLevel)}</Badge>
          <Badge tone="accent">{session.title ?? `会话 ${shortId(replay.sessionId)}`}</Badge>
        </div>
      </Card>

      <Card eyebrow="时间线" title="执行顺序">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {timelineSteps.map((step, index) => (
            <div className="panel-soft rounded-[1.1rem] p-4" key={`${index}-${step.label}`}>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">步骤 {index + 1}</div>
              <div className="mt-3 text-sm font-medium">{step.label}</div>
              {step.detail ? (
                <div className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">{step.detail}</div>
              ) : null}
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <Card eyebrow="关键分支" title="这次运行如何拆分处理">
          <div className="space-y-3">
            {replay.branches.map((branch) => (
              <div className="panel-soft rounded-[1.1rem] p-4" key={branch.id}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-medium">{branch.title ?? branch.type}</div>
                    <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                      {branch.summary ?? `${branch.requestCount ?? branch.requestIds.length} 个步骤`}
                    </div>
                    <div className="mono mt-2 text-xs text-[color:var(--text-soft)]">分支 {shortId(branch.id)}</div>
                  </div>
                  <Badge tone={genericStatusTone(branch.status)}>{genericStatusLabel(branch.status)}</Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card eyebrow="请求步骤" title="每一步做了什么">
          <DataTable
            headers={["步骤类型", "执行者", "接口 / 动作", "这一步做了什么", "结果", "状态码", "延迟", "判断记录"]}
            rows={replay.requests.map((request) => [
              <div key={`${request.id}-id`}>
                <div className="font-medium">{request.stepType ?? request.pathLabel ?? "请求步骤"}</div>
                <div className="mono text-xs text-[color:var(--text-soft)]">{shortId(request.id)}</div>
              </div>,
              requestActorLabel(request.actor),
              <div key={`${request.id}-path`}>
                <div>{request.pathLabel ?? request.path}</div>
                <div className="mono text-xs text-[color:var(--text-soft)]">{request.path}</div>
              </div>,
              request.summary ?? "本步没有补充摘要。",
              <Badge key={`${request.id}-outcome`} tone={outcomeTone(request.outcome)}>{outcomeLabel(request.outcome)}</Badge>,
              request.status,
              request.latency,
              request.artifactCount
            ])}
          />
        </Card>
      </div>

      <Card eyebrow="治理面板" title="这次运行接下来怎么处理">
        <div className="grid gap-3 md:grid-cols-3">
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            当前阶段：{run.stageLabel ?? evidenceLabel(run.evidenceLevel)}。{run.stageDetail ?? "先确认这次运行是否已经具备稳定标签。"}
          </div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            可用 Builder：{builderBadges.length ? builderBadges.join("、") : "暂时没有，需要继续补监督。"}
          </div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            下一步：{run.nextAction ?? "回到补标签或样本治理页面继续处理。"}
          </div>
        </div>
        {runBlockers.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {runBlockers.slice(0, 4).map((item) => (
              <Badge key={item} tone="warning">
                {item}
              </Badge>
            ))}
          </div>
        ) : null}
      </Card>
    </div>
  );
}
