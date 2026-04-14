import { getDashboardBundle } from "@/lib/data-source";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";

export default async function AccessPage() {
  const {
    bundle: { ingestSummary, sessions, workflowLanes },
    meta
  } = await getDashboardBundle();

  return (
    <div className="space-y-6">
      <PageHeader
        title="接入"
        description="先让 agent 或 benchmark 的 LLM 请求走 ClawGraph proxy，再确认第一条真实运行已经可见、可回放、可继续治理。"
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
              ingestSummary?.latestSessionId ?? "-"
            ]
          ]}
        />
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card eyebrow="推荐顺序" title="建议按这个顺序接入">
          <div className="grid gap-3">
            {[
              ["第一步：只切到 proxy", "只改 endpoint/base_url，让真实请求先稳定进入 ClawGraph。"],
              ["第二步：补稳定身份", "补 session/run/task 等 durable id，提升回放和分组精度。"],
              ["第三步：补关键语义", "只在 retry、fallback、route、task_completed 等节点补语义事件。"]
            ].map(([title, body]) => (
              <div className="panel-soft rounded-[1.15rem] p-4" key={title}>
                <div className="font-medium">{title}</div>
                <p className="mt-2 text-sm text-[color:var(--text-muted)]">{body}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card eyebrow="检查清单" title="当前覆盖情况">
          <div className="grid gap-3 md:grid-cols-2">
            {[
              `请求归属清晰度：${ingestSummary?.identityCoverage ?? "-"}`,
              `任务识别清晰度：${ingestSummary?.semanticCoverage ?? "-"}`,
              `待补基础标签运行：${ingestSummary?.needsAnnotationRuns ?? 0}`,
              `待人工确认运行：${ingestSummary?.needsReviewRuns ?? 0}`,
              `可导出运行：${ingestSummary?.readyForDatasetRuns ?? 0}`,
              `可评估运行：${ingestSummary?.readyForEvalRuns ?? 0}`,
              `接入流程阶段：${workflowLanes?.find((lane) => lane.id === "capture")?.count ?? 0} 条运行正在采集`,
              `数据源模式：${meta.statusText}`
            ].map((item) => (
              <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={item}>
                {item}
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card eyebrow="最近会话" title="用真实运行验证接入是否成功">
        <DataTable
          headers={["会话", "运行数", "请求数", "当前阶段", "下一步", "异常提示"]}
          rows={sessions.slice(0, 5).map((session) => [
            session.id,
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
