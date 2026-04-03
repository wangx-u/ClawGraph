import { getDashboardBundle } from "@/lib/data-source";
import { genericStatusLabel, genericStatusTone, riskLabel, riskTone, strengthLabel } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";

export default async function CoveragePage() {
  const {
    bundle: { coverageRows }
  } = await getDashboardBundle();

  return (
    <div className="space-y-6">
      <PageHeader
        title="覆盖策略"
        description="把 slice 质量、recipe fit 和 scorecard 证据，转成受控灰度、扩量或保留的可执行策略。"
        primaryAction={<Button href="/evaluation" variant="primary">更新覆盖决策</Button>}
        secondaryAction={<Button href="/feedback" variant="secondary">打开回流队列</Button>}
      />

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <Card eyebrow="切片覆盖矩阵" title="替代机会面" strong>
          <DataTable
            headers={["Slice", "Verifier", "风险", "复杂度", "Recipe", "模型带宽", "结论", "放量"]}
            rows={coverageRows.map((row) => [
              <span className="mono text-xs text-[color:var(--text-soft)]" key={`${row.sliceId}-id`}>{row.sliceId}</span>,
              strengthLabel(row.verifier),
              <Badge key={`${row.sliceId}-risk`} tone={riskTone(row.risk)}>{riskLabel(row.risk)}</Badge>,
              row.complexity,
              row.recipe,
              row.modelBand,
              <Badge key={`${row.sliceId}-verdict`} tone={genericStatusTone(row.verdict)}>{genericStatusLabel(row.verdict)}</Badge>,
              <Badge key={`${row.sliceId}-rollout`} tone={genericStatusTone(row.rollout)}>{genericStatusLabel(row.rollout)}</Badge>
            ])}
          />
        </Card>

        <Card eyebrow="护栏规则" title="Fallback 触发条件">
          <div className="space-y-3">
            {[
              "缺少 rollout history 或 deploy_sha",
              "回滚动作没有 approval artifact",
              "涉及跨服务 blast radius 但证据不足",
              "verifier fail 或误回滚率突增",
              "需要人工确认的高危生产动作"
            ].map((item) => (
              <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={item}>
                {item}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
