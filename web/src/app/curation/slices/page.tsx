import { getDashboardBundle } from "@/lib/data-source";
import { riskLabel, riskTone } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";

export default async function SliceRegistryPage() {
  const {
    bundle: { slices }
  } = await getDashboardBundle();
  const highRiskCount = slices.filter((slice) => slice.risk === "high").length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="策展 / 切片注册表"
        description="先定义稳定的任务切片，再去冻结训练批次、导出数据快照或做替代决策，避免后续口径漂移。"
        primaryAction={<Button href="/curation/candidates" variant="primary">查看候选池</Button>}
        secondaryAction={<Button href="/datasets" variant="secondary">打开数据集</Button>}
      />

      <div className="grid gap-4 md:grid-cols-3">
        <div className="surface-strong rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">已注册切片</div>
          <div className="mt-3 text-3xl font-semibold">{slices.length}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">高风险切片</div>
          <div className="mt-3 text-3xl font-semibold">{highRiskCount}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">默认训练用途</div>
          <div className="mt-3 text-lg font-semibold">training_candidate</div>
        </div>
      </div>

      <Card eyebrow="切片注册表" title="已登记切片" strong>
        <DataTable
          headers={["Slice", "任务族", "任务类型", "Taxonomy", "样本单元", "风险", "负责人"]}
          rows={slices.map((slice) => [
            <div key={`${slice.id}-id`}>
              <div className="font-medium">{slice.label ?? slice.id}</div>
              <div className="mono text-xs text-[color:var(--text-soft)]">{slice.id}</div>
            </div>,
            slice.taskFamily,
            slice.taskType,
            slice.taxonomyVersion,
            slice.sampleUnit,
            <Badge key={`${slice.id}-risk`} tone={riskTone(slice.risk)}>{riskLabel(slice.risk)}</Badge>,
            slice.owner
          ])}
        />
      </Card>
    </div>
  );
}
