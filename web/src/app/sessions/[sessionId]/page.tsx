import { getDashboardBundle } from "@/lib/data-source";
import { evidenceLabel, evidenceTone, shortId } from "@/lib/presenters";
import { formatPercent } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

export default async function SessionDetailPage({
  params
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  const {
    bundle: { sessions }
  } = await getDashboardBundle();
  const session = sessions.find((item) => item.id === sessionId) ?? sessions[0];

  if (!session) {
    return (
      <EmptyState
        actionHref="/sessions"
        actionLabel="返回会话收件箱"
        description="当前真实数据源里还没有可打开的会话详情。"
        title="会话不存在"
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={session.title ?? `会话 ${shortId(session.id)}`}
        description="从会话维度看清这批真实运行做了什么、当前卡在哪一步，以及是否已经能进入训练或验证。"
        primaryAction={<Button href={`/sessions/${session.id}/runs/${session.runs[0].id}/replay`} variant="primary">打开回放</Button>}
        secondaryAction={<Button href="/supervision" variant="secondary">进入监督</Button>}
      />

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Card eyebrow="会话摘要" title="证据状态" strong>
          <div className="grid gap-3 md:grid-cols-4">
            <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">证据等级</div><div className="mt-3 text-2xl font-semibold">{evidenceLabel(session.evidenceLevel)}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">运行数</div><div className="mt-3 text-2xl font-semibold">{session.runs.length}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">请求数</div><div className="mt-3 text-2xl font-semibold">{session.requests}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">分支数</div><div className="mt-3 text-2xl font-semibold">{session.branches}</div></div>
          </div>
          <div className="mt-4 text-sm text-[color:var(--text-muted)]">
            {session.summary ?? `${session.requests} 次请求，${session.branches} 条分支。`}
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            {session.userIds.map((userId) => (
              <Badge key={userId} tone="info">{userId}</Badge>
            ))}
            <Badge tone="neutral">会话 {shortId(session.id)}</Badge>
          </div>
        </Card>

        <Card eyebrow="当前阻塞与下一步" title={session.nextAction ?? "先打开最近运行"} >
          <div className="space-y-3">
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
              {session.nextAction ?? "先从最近一次运行开始，确认它处在采集、数据准备、复核还是导出阶段。"}
            </div>
            {session.anomalies.length ? (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700">
                当前最明显的问题：{session.anomalies[0]}
              </div>
            ) : null}
          </div>
        </Card>
      </div>

      <Card eyebrow="运行清单" title="当前会话的运行状态">
        <DataTable
          headers={["任务运行", "请求", "成功", "失败", "进行中", "分支", "显式覆盖", "判断记录", "状态", "操作"]}
          rows={session.runs.map((run) => [
            <div key={`${run.id}-id`}>
              <div className="font-medium">{run.title ?? run.id}</div>
              {run.summary ? (
                <div className="mt-1 text-sm text-[color:var(--text-muted)]">{run.summary}</div>
              ) : null}
              <div className="mono text-xs text-[color:var(--text-soft)]">运行 {shortId(run.id)}</div>
            </div>,
            run.requestCount,
            run.successCount,
            run.failureCount,
            run.openCount,
            run.branchCount,
            formatPercent(run.declaredRatio),
            run.artifactCount,
            <div className="flex flex-wrap gap-2" key={`${run.id}-badge`}>
              <Badge tone={evidenceTone(run.evidenceLevel)}>{evidenceLabel(run.evidenceLevel)}</Badge>
              {run.stageLabel ? <Badge tone="info">{run.stageLabel}</Badge> : null}
            </div>,
            <Button className="w-full" href={`/sessions/${session.id}/runs/${run.id}/replay`} key={`${run.id}-action`} variant="secondary">进入回放</Button>
          ])}
        />
      </Card>

      {session.anomalies.length ? (
        <Card eyebrow="异常摘要" title="当前会话待修复项">
          <div className="space-y-3">
            {session.anomalies.map((item) => (
              <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-700" key={item}>
                {item}
              </div>
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  );
}
