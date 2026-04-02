import { getDashboardBundle } from "@/lib/data-source";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";

export default async function EvalSuiteDetailPage({
  params
}: {
  params: Promise<{ suiteId: string }>;
}) {
  const { suiteId } = await params;
  const {
    bundle: { evalSuites, scorecards }
  } = await getDashboardBundle();
  const suite = evalSuites.find((item) => item.id === suiteId) ?? evalSuites[0];
  const suiteScorecards = suite
    ? scorecards.filter((scorecard) => scorecard.evalSuiteId === suite.id)
    : [];

  if (!suite) {
    return (
      <EmptyState
        actionHref="/evaluation"
        actionLabel="返回评测"
        description="当前还没有可查看的评测套件。先从 evaluation 页面创建一套。"
        title="评测套件不存在"
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={`评测套件 ${suite.id}`}
        description="从套件结构、candidate 指标和最新 recommendation 视角查看一个 slice 的替代决策依据。"
        primaryAction={<Button href="/coverage" variant="primary">更新覆盖决策</Button>}
        secondaryAction={<Button href="/evaluation" variant="secondary">返回评测</Button>}
      />

      <Card eyebrow="套件摘要" title={suite.kind} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">Slice</div><div className="mt-3 text-xl font-semibold">{suite.sliceId}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">类型</div><div className="mt-3 text-xl font-semibold">{suite.kind}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">样本数</div><div className="mt-3 text-xl font-semibold">{suite.items}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">状态</div><div className="mt-3 text-xl font-semibold">{genericStatusLabel(suite.status)}</div></div>
        </div>
      </Card>

      <Card eyebrow="决策面板" title="最新推荐">
        <Tabs active="指标" items={["指标", "阈值", "决策历史", "失败分析"]} />
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {suiteScorecards.map((scorecard) => (
            <div className="panel-soft rounded-[1.1rem] p-4" key={scorecard.id}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="mono text-xs text-[color:var(--text-soft)]">{scorecard.id}</div>
                  <div className="mt-2 text-lg font-medium">
                    {scorecard.candidateModel} vs {scorecard.baselineModel}
                  </div>
                </div>
                <Badge tone={genericStatusTone(scorecard.verdict)}>{genericStatusLabel(scorecard.verdict)}</Badge>
              </div>
              <div className="mt-4 space-y-2 text-sm text-[color:var(--text-muted)]">
                <div>成功率：{scorecard.successRate}</div>
                <div>Verifier：{scorecard.verifierRate}</div>
                <div>P95 延迟：{scorecard.p95Latency}</div>
                <div>Fallback：{scorecard.fallbackRate}</div>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
