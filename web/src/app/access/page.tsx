import { getDashboardBundle } from "@/lib/data-source";
import { shortId } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";

export default async function AccessPage() {
  const {
    bundle: { ingestSummary, sessions, workflowLanes },
    meta
  } = await getDashboardBundle();
  const latestSessionLabel =
    ingestSummary?.latestSessionTitle ?? ingestSummary?.latestRunTitle ?? ingestSummary?.latestSessionId ?? "-";
  const captureLane = workflowLanes?.find((lane) => lane.id === "capture");
  const annotateLane = workflowLanes?.find((lane) => lane.id === "annotate");
  const reviewLane = workflowLanes?.find((lane) => lane.id === "review");

  return (
    <div className="space-y-6">
      <PageHeader
        title="接入"
        description="先让 agent 或 benchmark 的 LLM 请求走 ClawGraph proxy，再确认第一条真实运行已经可见、可回放，并且足以进入后续数据与验证闭环。"
        primaryAction={<Button href="/flows/connect-runtime" variant="primary">打开接入流程</Button>}
        secondaryAction={<Button href="/sessions" variant="secondary">查看最近运行</Button>}
      />

      <Card eyebrow="连接状态" title="真实接入概览" strong>
        <DataTable
          headers={["数据源", "最近活动", "请求总数", "成功率", "进行中运行", "最新会话"]}
          rows={[
            [
              meta.statusText,
              ingestSummary?.latestActivity ?? "-",
              String(ingestSummary?.requestCount ?? 0),
              ingestSummary?.successRate ?? "-",
              String(ingestSummary?.inProgressRuns ?? 0),
              latestSessionLabel
            ]
          ]}
        />
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card eyebrow="当前进度" title="现在这条链路走到哪一步" strong>
          <div className="grid gap-3">
            {[
              [
                captureLane?.title ?? "1. 采集",
                `${captureLane?.count ?? 0} 条运行仍在接入或等待闭合。${captureLane?.detail ?? ""}`
              ],
              [
                annotateLane?.title ?? "2. 数据准备",
                `${annotateLane?.count ?? 0} 条运行还需要补齐基础标签、任务实例或基础判断。`
              ],
              [
                reviewLane?.title ?? "3. 人工复核",
                `${reviewLane?.count ?? 0} 条运行进入人工确认，确认后才能稳定入池。`
              ]
            ].map(([title, body]) => (
              <div className="panel-soft rounded-[1.15rem] p-4" key={title}>
                <div className="font-medium">{title}</div>
                <p className="mt-2 text-sm text-[color:var(--text-muted)]">{body}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card eyebrow="当前覆盖情况" title="接入质量与后续可用性">
          <div className="grid gap-3 md:grid-cols-2">
            {[
              ["请求归属清晰度", ingestSummary?.identityCoverage ?? "-", "能否稳定归到同一会话和运行。"],
              ["任务标签覆盖率", ingestSummary?.taskCoverage ?? ingestSummary?.semanticCoverage ?? "-", "能否看清任务类型、仓库和实例。"],
              ["决策语义覆盖率", ingestSummary?.decisionCoverage ?? ingestSummary?.semanticCoverage ?? "-", "是否已经补到 retry、fallback、task_completed 等关键节点。"],
              ["待补基础标签", String(ingestSummary?.needsAnnotationRuns ?? 0), "这些运行还不能直接进入候选池。"],
              ["待人工确认", String(ingestSummary?.needsReviewRuns ?? 0), "需要人工判定是否可入池或进入验证。"],
              ["可导出训练数据", String(ingestSummary?.readyForDatasetRuns ?? 0), "已经满足训练格式导出的基础条件。"],
              ["已生成验证资产", String(ingestSummary?.evaluationAssetCount ?? 0), "已经冻结并可用于模型对比。"],
              ["当前数据源", meta.statusText, `最近任务：${latestSessionLabel}${latestSessionLabel !== ingestSummary?.latestSessionId ? ` · 会话 ${shortId(ingestSummary?.latestSessionId ?? "-")}` : ""}`]
            ].map(([label, value, detail]) => (
              <div className="panel-soft rounded-2xl p-4" key={label}>
                <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">{label}</div>
                <div className="mt-3 text-xl font-semibold">{value}</div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">{detail}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card eyebrow="最近会话" title="用真实运行验证接入是否成功">
        <DataTable
          headers={["会话", "运行数", "请求数", "当前阶段", "下一步", "异常提示"]}
          rows={sessions.slice(0, 5).map((session) => [
            <div key={`${session.id}-cell`}>
              <div className="font-medium">{session.title ?? session.id}</div>
              <div className="mono text-xs text-[color:var(--text-soft)]">会话 {shortId(session.id)}</div>
            </div>,
            session.runs.length,
            session.requests,
            session.runs[0]?.stageLabel ?? "待观察",
            session.nextAction ?? session.runs[0]?.nextAction ?? "打开会话确认下一步",
            session.anomalies[0] ?? "无明显异常"
          ])}
        />
      </Card>
    </div>
  );
}
