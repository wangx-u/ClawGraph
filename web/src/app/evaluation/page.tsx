import { getDashboardBundle } from "@/lib/data-source";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { EvaluationWorkspace } from "@/components/dashboard/evaluation-workspace";

export default async function EvaluationPage() {
  const {
    bundle: { evalSuites, scorecards }
  } = await getDashboardBundle();

  if (!evalSuites.length && !scorecards.length) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="评测"
          description="当前真实数据源里还没有评测套件或评分卡。先生成评测 Cohort，再回来查看替代验证结果。"
          primaryAction={<Button href="/flows/validate-slice" variant="primary">查看验证流程</Button>}
          secondaryAction={<Button href="/coverage" variant="secondary">打开覆盖策略</Button>}
        />
        <EmptyState
          actionHref="/flows/validate-slice"
          actionLabel="创建评测流程"
          description="当 store 中出现 eval suite 或 scorecard 后，这里会自动切换成可交互的评分工作区。"
          title="还没有评测资产"
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="评测"
        description="围绕 slice 构建评测套件，对比 candidate 与 baseline，并沉淀明确的放量或保留决策。"
        primaryAction={<Button href="/flows/validate-slice" variant="primary">创建评测套件</Button>}
        secondaryAction={<Button href="/coverage" variant="secondary">打开覆盖策略</Button>}
      />

      <EvaluationWorkspace evalSuites={evalSuites} scorecards={scorecards} />
    </div>
  );
}
