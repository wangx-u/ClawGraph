import { getDashboardBundle } from "@/lib/data-source";
import { genericStatusLabel, genericStatusTone, outcomeLabel, outcomeTone } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";
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

  return (
    <div className="space-y-6">
      <PageHeader
        title={`回放 ${replay.runId}`}
        description="按执行顺序还原一个真实运行的请求、分支和语义事件，用于定位根因并判断它是否具备导出就绪度。"
        primaryAction={<Button href="/flows/investigate-failure" variant="primary">排查失败</Button>}
        secondaryAction={<Button href="/supervision" variant="secondary">补监督信号</Button>}
      />

      <Card eyebrow="回放摘要" title={`${replay.sessionId} / ${replay.runId}`} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">结果</div><div className="mt-3 text-2xl font-semibold">{outcomeLabel(run.outcome)}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">请求数</div><div className="mt-3 text-2xl font-semibold">{replay.requests.length}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">分支数</div><div className="mt-3 text-2xl font-semibold">{replay.branches.length}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">Artifacts</div><div className="mt-3 text-2xl font-semibold">{artifactCount}</div></div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge tone={outcomeTone(run.outcome)}>{outcomeLabel(run.outcome)}</Badge>
          <Badge tone="info">{run.avgLatency}</Badge>
          <Badge tone="accent">会话 {replay.sessionId}</Badge>
        </div>
      </Card>

      <Card eyebrow="时间线" title="执行顺序">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {replay.timeline.map((step, index) => (
            <div className="panel-soft rounded-[1.1rem] p-4" key={step}>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">步骤 {index + 1}</div>
              <div className="mt-3 text-sm leading-6">{step}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <Card eyebrow="分支树" title="Declared 与 Inferred 对照">
          <div className="space-y-3">
            {replay.branches.map((branch) => (
              <div className="panel-soft rounded-[1.1rem] p-4" key={branch.id}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="mono text-xs text-[color:var(--text-soft)]">{branch.id}</div>
                    <div className="mt-2 font-medium">{branch.type}</div>
                    <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                      {branch.source === "declared" ? "显式声明" : "推断恢复"} · 请求: {branch.requestIds.join(", ")}
                    </div>
                  </div>
                  <Badge tone={genericStatusTone(branch.status)}>{genericStatusLabel(branch.status)}</Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card eyebrow="请求跨度" title="Request Span 表">
          <DataTable
            headers={["请求", "执行者", "路径", "结果", "状态码", "延迟", "Artifacts"]}
            rows={replay.requests.map((request) => [
              <span className="mono text-xs text-[color:var(--text-soft)]" key={`${request.id}-id`}>{request.id}</span>,
              request.actor,
              request.path,
              <Badge key={`${request.id}-outcome`} tone={outcomeTone(request.outcome)}>{outcomeLabel(request.outcome)}</Badge>,
              request.status,
              request.latency,
              request.artifactCount
            ])}
          />
        </Card>
      </div>

      <Card eyebrow="上下文面板" title="回放配套上下文">
        <Tabs active="导出就绪度" items={["Artifacts 叠层", "Payload 预览", "语义事件", "导出就绪度"]} />
        <div className="mt-5 grid gap-3 md:grid-cols-3">
          {[
            "sft：就绪，成功分支里 metrics / logs / rollout 12 条 request 已可导出。",
            "preference：已抽取 rollback vs continue-observe 的 1 组偏好对，但仍缺更多 approval 样本。",
            "binary_rl：就绪，整次 incident run 已具备最终恢复结果与 verifier 记录。"
          ].map((item) => (
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={item}>
              {item}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
