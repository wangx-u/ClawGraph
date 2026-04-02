import { getDashboardBundle } from "@/lib/data-source";
import { evidenceTone } from "@/lib/presenters";
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
        title={`会话 ${session.id}`}
        description="从会话维度审查证据健康度、运行质量和异常项，再判断它是否适合进入回放、监督或策展流程。"
        primaryAction={<Button href={`/sessions/${session.id}/runs/${session.runs[0].id}/replay`} variant="primary">打开回放</Button>}
        secondaryAction={<Button href="/supervision" variant="secondary">进入监督</Button>}
      />

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Card eyebrow="会话摘要" title="证据状态" strong>
          <div className="grid gap-3 md:grid-cols-4">
            <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">证据等级</div><div className="mt-3 text-2xl font-semibold">{session.evidenceLevel}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">运行数</div><div className="mt-3 text-2xl font-semibold">{session.runs.length}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">请求数</div><div className="mt-3 text-2xl font-semibold">{session.requests}</div></div>
            <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">分支数</div><div className="mt-3 text-2xl font-semibold">{session.branches}</div></div>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            {session.userIds.map((userId) => (
              <Badge key={userId} tone="info">{userId}</Badge>
            ))}
          </div>
        </Card>

        <Card eyebrow="建议动作" title="当前最优下一步">
          <div className="space-y-3">
            {[
              "在冻结任何 cohort 之前，先回看最近失败的 run。",
              "对于仍处于 E0 或 E1 的运行，优先执行 openclaw-defaults。",
              "进入策展前，先补齐 task_instance_key 与核心语义事件。"
            ].map((item) => (
              <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={item}>
                {item}
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card eyebrow="运行清单" title="Run 质量表">
        <DataTable
          headers={["Run", "请求", "成功", "失败", "Open", "分支", "Declared", "Artifacts", "证据", "动作"]}
          rows={session.runs.map((run) => [
            <span className="mono text-xs text-[color:var(--text-soft)]" key={`${run.id}-id`}>{run.id}</span>,
            run.requestCount,
            run.successCount,
            run.failureCount,
            run.openCount,
            run.branchCount,
            formatPercent(run.declaredRatio),
            run.artifactCount,
            <Badge key={`${run.id}-badge`} tone={evidenceTone(run.evidenceLevel)}>{run.evidenceLevel}</Badge>,
            <Button className="w-full" href={`/sessions/${session.id}/runs/${run.id}/replay`} key={`${run.id}-action`} variant="secondary">回放</Button>
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
