import { getDashboardBundle } from "@/lib/data-source";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";

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
  const actionRuns = (workflowRuns ?? []).filter(
    (run) => run.stage === "annotate" || run.stage === "augment" || run.stage === "review"
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="数据准备"
        description="在不改写底层事实的前提下，先完成自动清理、任务判断和质量标注；只有需要人工确认的运行才进入复核。"
        primaryAction={<Button href="/flows/build-dataset" variant="primary">进入导出流程</Button>}
        secondaryAction={<Button href={latestReplayHref} variant="secondary">返回最近回放</Button>}
      />

      <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <Card eyebrow="自动准备" title="系统已经自动完成的准备项" strong>
          <div className="space-y-3">
            {[
              ["基础任务标签", "为每条运行补齐 task instance、模板和来源信息。"],
              ["结果评分", "根据请求闭合情况和验证结果生成统一质量分。"],
              ["分支偏好", "识别更优路径，为偏好学习或 RL 保留素材。"],
              ["版本化判断", "把自动判断和人工修正都写成可追溯 artifact。"]
            ].map(([title, detail]) => (
              <div className="panel-soft rounded-2xl p-4" key={title}>
                <div className="font-medium">{title}</div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                  {detail}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card eyebrow="当前结果" title="已经写入的版本化判断">
          <DataTable
            headers={["Artifact", "类型", "目标", "生产者", "状态", "置信度", "版本"]}
            rows={artifacts.map((artifact) => [
              <span className="mono text-xs text-[color:var(--text-soft)]" key={`${artifact.id}-id`}>{artifact.id}</span>,
              artifact.type,
              <span className="mono text-xs text-[color:var(--text-soft)]" key={`${artifact.id}-target`}>{artifact.targetRef}</span>,
              artifact.producer,
              <Badge key={`${artifact.id}-status`} tone={genericStatusTone(artifact.status)}>{genericStatusLabel(artifact.status)}</Badge>,
              artifact.confidence,
              artifact.version
            ])}
          />
        </Card>
      </div>

      <Card eyebrow="当前任务" title="按治理流程整理">
        <div className="grid gap-3 md:grid-cols-3">
          {actionRuns.length ? (
            actionRuns.slice(0, 3).map((run) => (
              <div className="panel-soft rounded-2xl p-4" key={run.runId}>
                <div className="font-medium">{run.title ?? run.runId}</div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">{run.summary ?? run.stageDetail}</div>
                <div className="mt-3 text-sm text-[color:var(--text-muted)]">下一步：{run.nextAction}</div>
                <div className="mono mt-2 text-xs text-[color:var(--text-soft)]">运行 {run.runId}</div>
              </div>
            ))
          ) : (
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
              当前没有需要额外处理的运行。新采集的数据会在自动清理、判断和复核后出现在这里。
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
