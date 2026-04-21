import { getDashboardBundle } from "@/lib/data-source";
import type { Candidate, StatusTone } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";

function candidateDecision(candidate: Candidate): {
  label: string;
  tone: StatusTone;
  reason: string;
  destination: string;
} {
  if (candidate.status === "eligible") {
    return {
      label: "建议进入训练批次",
      tone: "success",
      reason:
        candidate.quality >= 0.85 && candidate.verifier >= 0.85
          ? "质量分和 verifier 都通过当前阈值，可以直接进入下一版训练批次。"
          : "虽然接近阈值，但当前仍满足入池条件，可随训练批次一起冻结。",
      destination: "进入训练批次"
    };
  }

  if (candidate.status === "holdout") {
    return {
      label: "建议保留为保留集",
      tone: "accent",
      reason: "这条样本更适合作为评测或回归保留集，避免训练和验证口径混用。",
      destination: "保留给评测 / 回归"
    };
  }

  if (candidate.quality < 0.6 || candidate.verifier < 0.6) {
    return {
      label: "需要人工判定去留",
      tone: "warning",
      reason: "质量分和 verifier 都偏低，先确认是否剔除、返工或仅保留为诊断样本。",
      destination: "人工复核后决定"
    };
  }

  return {
    label: "需要人工复核",
    tone: "warning",
    reason: "虽然样本已形成候选，但仍需确认动作正确性、模板边界或业务含义。",
    destination: "复核后再入池"
  };
}

function candidateTitle(candidate: Candidate) {
  return candidate.taskLabel ?? candidate.runTitle ?? candidate.taskInstanceKey;
}

export default async function CandidatePoolPage() {
  const {
    bundle: { candidates, cohorts }
  } = await getDashboardBundle();
  const eligibleCount = candidates.filter((item) => item.status === "eligible").length;
  const reviewCount = candidates.filter((item) => item.status === "review").length;
  const holdoutCount = candidates.filter((item) => item.status === "holdout").length;
  const trainingCohort = cohorts.find((cohort) => cohort.purpose === "训练") ?? cohorts[0];
  const cohortHref = trainingCohort ? `/curation/cohorts/${trainingCohort.id}` : "/datasets";
  const manualQueue = [...candidates]
    .sort((left, right) => {
      if (left.status === right.status) {
        return (left.quality + left.verifier) - (right.quality + right.verifier);
      }
      if (left.status === "review") {
        return -1;
      }
      if (right.status === "review") {
        return 1;
      }
      return 0;
    });

  return (
    <div className="space-y-6">
      <PageHeader
        title="人工筛选工作区"
        description="先看每条候选样本的建议结论、原因和去向，再决定哪些进入训练批次，哪些进入保留集，哪些需要返工。"
        primaryAction={<Button href={cohortHref} variant="primary">查看当前冻结结果</Button>}
        secondaryAction={<Button href="/datasets" variant="secondary">打开数据集流</Button>}
      />

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
        <div className="surface-strong rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">候选总量</div>
          <div className="mt-3 text-3xl font-semibold">{candidates.length}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">建议直接入池</div>
          <div className="mt-3 text-3xl font-semibold">{eligibleCount}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">待人工复核</div>
          <div className="mt-3 text-3xl font-semibold">{reviewCount}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">保留为保留集</div>
          <div className="mt-3 text-3xl font-semibold">{holdoutCount}</div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.12fr_0.88fr]">
        <Card eyebrow="人工复核队列" title="先处理这些候选决定" strong>
          <div className="space-y-3">
            {manualQueue.length ? (
              manualQueue.slice(0, 4).map((candidate) => {
                const decision = candidateDecision(candidate);
                return (
                  <div className="panel-soft rounded-[1.15rem] p-4" key={candidate.runId}>
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-xs text-[color:var(--text-soft)]">运行 {candidate.runId}</div>
                        <div className="mt-2 text-base font-medium">{candidateTitle(candidate)}</div>
                        <p className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">{decision.reason}</p>
                      </div>
                      <Badge tone={decision.tone}>{decision.label}</Badge>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      <div className="tech-highlight rounded-[1.05rem] p-4">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">质量分</div>
                        <div className="mt-2 text-2xl font-semibold">{candidate.quality.toFixed(2)}</div>
                      </div>
                      <div className="panel-soft rounded-[1.05rem] p-4">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Verifier</div>
                        <div className="mt-2 text-2xl font-semibold">{candidate.verifier.toFixed(2)}</div>
                      </div>
                      <div className="panel-soft rounded-[1.05rem] p-4">
                        <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">去向</div>
                        <div className="mt-2 text-sm font-medium">{decision.destination}</div>
                      </div>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <Badge tone="info">来源 {candidate.source}</Badge>
                      <Badge tone="neutral">Cluster {candidate.clusterId}</Badge>
                      <Badge tone="neutral">Template {candidate.templateHash}</Badge>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="panel-soft rounded-[1.15rem] p-4 text-sm text-[color:var(--text-muted)]">
                当前没有待筛选候选。新样本会在自动判断后进入这里，再决定是否冻结进训练批次。
              </div>
            )}
          </div>
        </Card>

        <Card eyebrow="筛选原则" title="如何决定入池、复核和保留集">
          <div className="space-y-3">
            {[
              {
                title: "通过阈值就尽快入池",
                detail: "质量分和 verifier 都稳定时，不要让样本长期滞留在人工队列中。"
              },
              {
                title: "边界样本先人工确认",
                detail: "接近阈值、动作有争议或模板边界模糊的样本，先确认再决定是否纳入训练。"
              },
              {
                title: "保留集只做验证不用训练",
                detail: "高价值回归样本和特殊场景要保留给评测，避免训练和验证污染。"
              },
              {
                title: "技术字段只做追溯",
                detail: "cluster、template 和 run id 用于回查，不应该成为用户先理解页面的前提。"
              }
            ].map((item) => (
              <div className="panel-soft rounded-[1.1rem] p-4" key={item.title}>
                <div className="font-medium">{item.title}</div>
                <p className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">{item.detail}</p>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card eyebrow="候选池明细" title="按决策方式查看候选样本">
        <DataTable
          headers={["候选运行", "建议结论", "为什么", "质量 / Verifier", "去向"]}
          rows={candidates.map((candidate) => {
            const decision = candidateDecision(candidate);
            return [
              <div key={`${candidate.runId}-id`}>
                <div className="font-medium">{candidateTitle(candidate)}</div>
                <div className="mono mt-1 text-xs text-[color:var(--text-soft)]">运行 {candidate.runId}</div>
                <div className="mt-2 text-xs text-[color:var(--text-muted)]">
                  Cluster {candidate.clusterId} · Template {candidate.templateHash}
                </div>
              </div>,
              <Badge key={`${candidate.runId}-status`} tone={decision.tone}>
                {decision.label}
              </Badge>,
              decision.reason,
              <div key={`${candidate.runId}-metrics`}>
                <div>质量 {candidate.quality.toFixed(2)}</div>
                <div className="mt-1 text-sm text-[color:var(--text-muted)]">Verifier {candidate.verifier.toFixed(2)}</div>
              </div>,
              <div key={`${candidate.runId}-destination`}>
                <div>{decision.destination}</div>
                <div className="mt-1 text-sm text-[color:var(--text-muted)]">来源 {candidate.source}</div>
              </div>
            ];
          })}
        />
      </Card>
    </div>
  );
}
