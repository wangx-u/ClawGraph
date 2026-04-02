import { getDashboardBundle } from "@/lib/data-source";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";

export default async function EvaluationPage() {
  const {
    bundle: { evalSuites, scorecards }
  } = await getDashboardBundle();

  return (
    <div className="space-y-6">
      <PageHeader
        title="评测"
        description="围绕 slice 构建评测套件，对比 candidate 与 baseline，并沉淀明确的放量或保留决策。"
        primaryAction={<Button href="/flows/validate-slice" variant="primary">创建评测套件</Button>}
        secondaryAction={<Button href="/coverage" variant="secondary">打开覆盖策略</Button>}
      />

      <Card eyebrow="套件看板" title="评测套件" strong>
        <DataTable
          headers={["Suite", "Slice", "类型", "来源 Cohort", "状态", "样本数", "动作"]}
          rows={evalSuites.map((suite) => [
            <span className="mono text-xs text-[color:var(--text-soft)]" key={`${suite.id}-id`}>{suite.id}</span>,
            suite.sliceId,
            suite.kind,
            suite.cohortId,
            <Badge key={`${suite.id}-status`} tone={genericStatusTone(suite.status)}>{genericStatusLabel(suite.status)}</Badge>,
            suite.items,
            <Button href={`/evaluation/${suite.id}`} key={`${suite.id}-action`} variant="secondary">打开</Button>
          ])}
        />
      </Card>

      <Card eyebrow="评分卡看板" title="候选模型与基线对比">
        <DataTable
          headers={["Scorecard", "Candidate", "Baseline", "结论", "成功率", "Verifier", "P95", "成本", "Fallback"]}
          rows={scorecards.map((scorecard) => [
            <span className="mono text-xs text-[color:var(--text-soft)]" key={`${scorecard.id}-id`}>{scorecard.id}</span>,
            scorecard.candidateModel,
            scorecard.baselineModel,
            <Badge key={`${scorecard.id}-verdict`} tone={genericStatusTone(scorecard.verdict)}>{genericStatusLabel(scorecard.verdict)}</Badge>,
            scorecard.successRate,
            scorecard.verifierRate,
            scorecard.p95Latency,
            scorecard.cost,
            scorecard.fallbackRate
          ])}
        />
      </Card>
    </div>
  );
}
