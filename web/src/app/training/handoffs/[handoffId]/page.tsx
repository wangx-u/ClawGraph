import { getDashboardBundle } from "@/lib/data-source";
import { evaluateLaunchReadiness, launchFieldText } from "@/lib/launch-control";
import { getModelCandidate, getRouterHandoff } from "@/lib/training-registry";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

export default async function TrainingHandoffDetailPage({
  params
}: {
  params: Promise<{ handoffId: string }>;
}) {
  const { handoffId } = await params;
  const { bundle } = await getDashboardBundle();
  const handoff = getRouterHandoff(bundle, handoffId);

  if (!handoff) {
    return (
        <EmptyState
          actionHref="/training"
          actionLabel="返回训练资产"
          description="当前还没有可查看的交接包。先从放量决策生成一份路由交接清单。"
          title="交接包不存在"
        />
    );
  }

  const candidate = getModelCandidate(bundle, handoff.candidateModelId);
  const readiness = evaluateLaunchReadiness(handoff);
  const checklist = [
    {
      label: "切流范围与流量比例",
      pass: readiness.trafficScopeReady && readiness.rolloutReady,
      detail: `${launchFieldText(handoff.trafficScope, "待确认")} · ${handoff.rolloutPercentage ? `${handoff.rolloutPercentage}%` : "待补首轮比例"}`
    },
    {
      label: "审批签核",
      pass: readiness.approvalReady && readiness.approverReady,
      detail: `${genericStatusLabel(handoff.approvalStatus ?? "pending_approval")} · ${launchFieldText(handoff.approver, "待指定")}`
    },
    {
      label: "Router 确认",
      pass: readiness.routerAckReady,
      detail: handoff.routerAckAt
        ? `${handoff.routerAckBy ?? "router"} · ${handoff.routerAckAt}`
        : genericStatusLabel(handoff.routerAckStatus ?? "awaiting_ack")
    },
    {
      label: "监控与回滚负责人",
      pass: readiness.monitorReady && readiness.rollbackOwnerReady,
      detail: `${launchFieldText(handoff.monitorSource, "待补监控来源")} · ${launchFieldText(handoff.rollbackOwner, "待指定")}`
    }
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={handoff.title}
        description="查看一个候选模型如何带着切流范围、审批、router ack 和 rollback 条件进入真正可执行的上线控制面。"
        primaryAction={<Button href="/coverage" variant="primary">返回上线控制面</Button>}
        secondaryAction={candidate ? <Button href={`/training/candidates/${candidate.id}`} variant="secondary">查看候选模型</Button> : undefined}
      />

      <Card eyebrow="交接摘要" title={handoff.sliceLabel ?? handoff.sliceId} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">建议阶段</div>
            <div className="mt-3"><Badge tone={genericStatusTone(handoff.stage)}>{genericStatusLabel(handoff.stage)}</Badge></div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">当前决策</div>
            <div className="mt-3 text-lg font-semibold">{genericStatusLabel(handoff.decision)}</div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">Route Mode</div>
            <div className="mt-3 text-lg font-semibold">{handoff.routeMode ?? "待补充"}</div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">策略版本</div>
            <div className="mt-3 text-lg font-semibold">{handoff.coveragePolicyVersion}</div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge tone={genericStatusTone(handoff.approvalStatus ?? "pending_approval")}>
            {genericStatusLabel(handoff.approvalStatus ?? "pending_approval")}
          </Badge>
          <Badge tone={genericStatusTone(handoff.routerAckStatus ?? "awaiting_ack")}>
            {genericStatusLabel(handoff.routerAckStatus ?? "awaiting_ack")}
          </Badge>
          {handoff.rolloutPercentage ? <Badge tone="info">{handoff.rolloutPercentage}% 流量</Badge> : null}
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card eyebrow="执行条件" title="这份交接现在是否可执行">
          <div className="space-y-3 text-sm text-[color:var(--text-muted)]">
            <div className="panel-soft rounded-2xl p-4">切流范围：{launchFieldText(handoff.trafficScope, "待确认")}</div>
            <div className="panel-soft rounded-2xl p-4">流量比例：{handoff.rolloutPercentage ? `${handoff.rolloutPercentage}%` : "待补首轮比例"}</div>
            <div className="panel-soft rounded-2xl p-4">审批：{genericStatusLabel(handoff.approvalStatus ?? "pending_approval")} · {launchFieldText(handoff.approver, "待指定")}</div>
            <div className="panel-soft rounded-2xl p-4">
              Router Ack：{genericStatusLabel(handoff.routerAckStatus ?? "awaiting_ack")}
              {handoff.routerAckAt ? ` · ${handoff.routerAckBy ?? "router"} · ${handoff.routerAckAt}` : ""}
            </div>
            <div className="panel-soft rounded-2xl p-4">监控来源：{launchFieldText(handoff.monitorSource, "待补监控来源")}</div>
            <div className="panel-soft rounded-2xl p-4">执行窗口：{launchFieldText(handoff.executionWindow, "待补充")}</div>
            <div className="tech-highlight rounded-2xl p-4">
              业务判断：这份交接{readiness.executable ? "已经满足上线执行条件。" : "还缺执行前条件，不能直接切流。"}
            </div>
          </div>
          {!readiness.executable ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {readiness.blockers.map((item) => (
                <Badge key={item} tone="warning">
                  {item}
                </Badge>
              ))}
            </div>
          ) : null}
          <details className="mt-4 panel-soft rounded-2xl p-4">
            <summary className="cursor-pointer text-sm font-medium text-[color:var(--text)]">查看技术明细</summary>
            <div className="mt-3 grid gap-3 text-xs text-[color:var(--text-soft)]">
              <div>Promotion：<span className="mono">{handoff.promotionDecisionId}</span></div>
              <div>交接清单：<span className="mono">{handoff.manifestPath}</span></div>
              {handoff.routeConfig ? (
                <pre className="overflow-x-auto rounded-2xl bg-slate-950/95 p-4 text-xs text-slate-100">
                  {JSON.stringify(handoff.routeConfig, null, 2)}
                </pre>
              ) : null}
            </div>
          </details>
        </Card>

        <Card eyebrow="回滚护栏" title="哪些条件会阻止继续放量">
          <div className="space-y-3">
            {checklist.map((item) => (
              <div className="panel-soft rounded-2xl p-4" key={item.label}>
                <div className="flex items-start justify-between gap-3">
                  <div className="font-medium">{item.label}</div>
                  <Badge tone={item.pass ? "success" : "warning"}>{item.pass ? "完成" : "待补"}</Badge>
                </div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">{item.detail}</div>
              </div>
            ))}
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
              回滚负责人：{launchFieldText(handoff.rollbackOwner, "待指定")}
            </div>
            {(handoff.rollbackConditions?.length ? handoff.rollbackConditions : ["当前未配置 rollback 条件"]).map((item) => (
              <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={item}>
                {item}
              </div>
            ))}
            {handoff.promotionSummary ? (
              <div className="tech-highlight rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
                {handoff.promotionSummary}
              </div>
            ) : null}
          </div>
        </Card>
      </div>
    </div>
  );
}
