import { getDashboardBundle } from "@/lib/data-source";
import {
  buildLaunchControlEntries,
  isActionableLaunchBlocker,
  isResolvedNonLaunchDecision,
  launchFieldText
} from "@/lib/launch-control";
import { genericStatusLabel, genericStatusTone, riskLabel, riskTone, strengthLabel } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";

export default async function CoveragePage() {
  const {
    bundle: { coverageGuardrails, coverageRows, routerHandoffs }
  } = await getDashboardBundle();
  const launchRows = buildLaunchControlEntries(coverageRows, routerHandoffs ?? []).map((row) => ({
    ...row,
    nextAction: row.executable
      ? "可以按当前范围执行首轮 canary，并在窗口内复查指标与回滚信号。"
      : row.decision === "promote"
        ? row.blockers[0] ?? "先补齐上线条件，再执行切流。"
        : "继续保留离线或回到数据闭环补齐证据。"
  }));
  const featuredLaunch =
    launchRows.find((row) => row.executable) ??
    launchRows.find((row) => row.decision === "promote") ??
    launchRows[0];
  const executableCount = launchRows.filter((row) => row.executable).length;
  const pendingApprovalCount = launchRows.filter((row) => row.decision === "promote" && !row.approvalReady).length;
  const awaitingAckCount = launchRows.filter(
    (row) => row.decision === "promote" && row.approvalReady && !row.routerAckReady
  ).length;
  const blockedCount = launchRows.filter((row) => isActionableLaunchBlocker(row)).length;
  const heldCount = launchRows.filter((row) => isResolvedNonLaunchDecision(row)).length;
  const featuredLaunchStateLabel = featuredLaunch
    ? featuredLaunch.executable
      ? "可执行"
      : isResolvedNonLaunchDecision(featuredLaunch)
        ? "保持离线"
        : "待补条件"
    : "待补条件";
  const featuredChecklist = featuredLaunch
    ? [
        ...(isResolvedNonLaunchDecision(featuredLaunch)
          ? [
              {
                label: "当前决策已收口",
                pass: true,
                detail: `${genericStatusLabel(featuredLaunch.decision ?? "pending")} · ${genericStatusLabel(featuredLaunch.promotionStage ?? featuredLaunch.recommendedStage)}`
              },
              {
                label: "监控与回流线索",
                pass: Boolean(featuredLaunch.monitorSource || featuredLaunch.rollbackConditions?.length),
                detail: featuredLaunch.monitorSource
                  ? launchFieldText(featuredLaunch.monitorSource, "待补监控来源")
                  : featuredLaunch.rollbackConditions?.join("；") || "当前还没有绑定明确监控或回滚线索。"
              },
              {
                label: "下一步",
                pass: true,
                detail: featuredLaunch.nextAction
              }
            ]
          : [
              {
                label: "切流范围已锁定",
                pass: featuredLaunch.trafficScopeReady && featuredLaunch.rolloutReady,
                detail: `${launchFieldText(featuredLaunch.trafficScope, "待确认")} · ${featuredLaunch.rolloutPercentage ? `${featuredLaunch.rolloutPercentage}%` : "待补首轮比例"}`
              },
              {
                label: "审批已签核",
                pass: featuredLaunch.approvalReady && featuredLaunch.approverReady,
                detail: `${genericStatusLabel(featuredLaunch.approvalStatus ?? "pending_approval")} · ${launchFieldText(featuredLaunch.approver, "待指定")}`
              },
              {
                label: "Router 已确认",
                pass: featuredLaunch.routerAckReady,
                detail: featuredLaunch.routerAckAt
                  ? `${featuredLaunch.routerAckBy ?? "router"} · ${featuredLaunch.routerAckAt}`
                  : genericStatusLabel(featuredLaunch.routerAckStatus ?? "awaiting_ack")
              },
              {
                label: "监控与回滚负责人已绑定",
                pass: featuredLaunch.monitorReady && featuredLaunch.rollbackOwnerReady,
                detail: `${launchFieldText(featuredLaunch.monitorSource, "待补监控来源")} · ${launchFieldText(featuredLaunch.rollbackOwner, "待指定")}`
              }
            ])
      ]
    : [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="上线控制面"
        description="把 slice 质量、交接包、审批、router ack 和回滚监控收敛到一个上线接替面，明确谁能现在执行 canary，谁还被阻塞。"
        primaryAction={
          <Button href={featuredLaunch?.handoff ? `/training/handoffs/${featuredLaunch.handoff.id}` : "/training"} variant="primary">
            {featuredLaunch?.handoff ? "打开当前交接包" : "返回模型接替"}
          </Button>
        }
        secondaryAction={<Button href="/feedback" variant="secondary">打开回流队列</Button>}
      />

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-5">
        <div className="surface-strong rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">现在可执行</div>
          <div className="mt-3 text-3xl font-semibold">{executableCount}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">待审批</div>
          <div className="mt-3 text-3xl font-semibold">{pendingApprovalCount}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">待 Router Ack</div>
          <div className="mt-3 text-3xl font-semibold">{awaitingAckCount}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">待补上线条件</div>
          <div className="mt-3 text-3xl font-semibold">{blockedCount}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">保持离线 / 回退</div>
          <div className="mt-3 text-3xl font-semibold">{heldCount}</div>
        </div>
      </div>

      {featuredLaunch ? (
        <Card
          action={
            featuredLaunch.handoff ? (
              <Button href={`/training/handoffs/${featuredLaunch.handoff.id}`} variant="primary">
                打开交接详情
              </Button>
            ) : undefined
          }
          eyebrow="当前控制面"
          title={`${featuredLaunch.sliceLabel ?? featuredLaunch.sliceId} · ${featuredLaunchStateLabel}`}
          strong
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              tone={
                featuredLaunch.executable
                  ? "success"
                  : isResolvedNonLaunchDecision(featuredLaunch)
                    ? genericStatusTone(featuredLaunch.decision ?? featuredLaunch.recommendedStage)
                    : "warning"
              }
            >
              {featuredLaunch.executable
                ? "可执行 Canary"
                : isResolvedNonLaunchDecision(featuredLaunch)
                  ? "已收口为离线决策"
                  : "尚不可执行"}
            </Badge>
            <Badge tone={genericStatusTone(featuredLaunch.decision ?? "pending")}>
              {genericStatusLabel(featuredLaunch.decision ?? "pending")}
            </Badge>
            <Badge tone={genericStatusTone(featuredLaunch.promotionStage ?? featuredLaunch.recommendedStage)}>
              {genericStatusLabel(featuredLaunch.promotionStage ?? featuredLaunch.recommendedStage)}
            </Badge>
          </div>
          <p className="mt-4 max-w-3xl text-sm leading-6 text-[color:var(--text-muted)]">{featuredLaunch.nextAction}</p>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {featuredChecklist.map((item) => (
              <div className="panel-soft rounded-[1.1rem] p-4" key={item.label}>
                <div className="flex items-start justify-between gap-3">
                  <div className="text-sm font-medium">{item.label}</div>
                  <Badge tone={item.pass ? "success" : "warning"}>{item.pass ? "完成" : "待补"}</Badge>
                </div>
                <div className="mt-3 text-sm leading-6 text-[color:var(--text-muted)]">{item.detail}</div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card eyebrow="切流矩阵" title="所有上线接替项" strong>
          <div className="space-y-3">
            {launchRows.map((row) => (
              <div className="panel-soft rounded-[1.15rem] p-4" key={row.sliceId}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="font-medium">{row.sliceLabel ?? row.sliceId}</div>
                    <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                      {row.candidateModel} · {row.recipe} · Verifier {strengthLabel(row.verifier)}
                    </div>
                    <div className="mt-3 grid gap-2 text-sm text-[color:var(--text-muted)]">
                      <div>切流范围：{launchFieldText(row.trafficScope, "待确认")}</div>
                      <div>当前流量：{row.rolloutPercentage ? `${row.rolloutPercentage}%` : "待补首轮比例"}</div>
                      <div>审批：{genericStatusLabel(row.approvalStatus ?? "pending_approval")} · {launchFieldText(row.approver, "待指定")}</div>
                      <div>Router Ack：{genericStatusLabel(row.routerAckStatus ?? "awaiting_ack")}{row.routerAckAt ? ` · ${row.routerAckAt}` : ""}</div>
                      <div>监控来源：{launchFieldText(row.monitorSource, "待补监控来源")}</div>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <Badge
                      tone={
                        row.executable
                          ? "success"
                          : isResolvedNonLaunchDecision(row)
                            ? genericStatusTone(row.decision ?? row.recommendedStage)
                            : genericStatusTone(row.approvalStatus ?? row.decision ?? "pending")
                      }
                    >
                      {row.executable
                        ? "可执行"
                        : isResolvedNonLaunchDecision(row)
                          ? "已收口"
                          : "待补条件"}
                    </Badge>
                    {row.handoff ? (
                      <Button href={`/training/handoffs/${row.handoff.id}`} variant="ghost">交接详情</Button>
                    ) : null}
                  </div>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Badge tone={riskTone(row.risk)}>{riskLabel(row.risk)}</Badge>
                  <Badge tone={genericStatusTone(row.verdict)}>{genericStatusLabel(row.verdict)}</Badge>
                  <Badge tone={genericStatusTone(row.recommendedStage)}>{genericStatusLabel(row.recommendedStage)}</Badge>
                </div>
                {isActionableLaunchBlocker(row) && row.blockers.length ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {row.blockers.slice(0, 3).map((item) => (
                      <Badge key={`${row.key}-${item}`} tone="warning">
                        {item}
                      </Badge>
                    ))}
                  </div>
                ) : null}
                <details className="mt-4 panel-soft rounded-2xl p-4">
                  <summary className="cursor-pointer text-sm font-medium text-[color:var(--text)]">查看技术明细</summary>
                  <div className="mt-3 grid gap-2 text-xs text-[color:var(--text-soft)]">
                    <div>Slice：<span className="mono">{row.sliceId}</span></div>
                    {row.handoff ? <div>Handoff：<span className="mono">{row.handoff.id}</span></div> : null}
                    <div>Coverage Policy：<span className="mono">{row.coveragePolicyVersion ?? "待补充"}</span></div>
                  </div>
                </details>
              </div>
            ))}
          </div>
        </Card>

        <Card eyebrow="执行清单" title="执行前必须确认">
          <div className="space-y-3">
            {[
              "先锁定切流范围和初始流量比例，再让 router 执行变更。",
              "审批人、router ack、监控来源和 rollback owner 缺一不可。",
              "所有回滚条件都必须可观测，并且能回流到 feedback 队列。",
              "没有 handoff 的 slice 只能停留在离线或待决策状态。"
            ].map((item) => (
              <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={item}>{item}</div>
            ))}
            <div className="tech-highlight rounded-2xl p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">全局回滚护栏</div>
              <div className="mt-3 space-y-2 text-sm text-[color:var(--text-muted)]">
                {(coverageGuardrails?.length
                  ? coverageGuardrails
                  : ["当前还没有从 promotion decision 中读取到真实 rollback 条件。"]
                ).map((item) => (
                  <div key={item}>{item}</div>
                ))}
              </div>
            </div>
            {featuredLaunch?.handoff ? (
              <Button className="w-full" href={`/training/handoffs/${featuredLaunch.handoff.id}`} variant="primary">
                进入当前交接包
              </Button>
            ) : null}
          </div>
        </Card>
      </div>
    </div>
  );
}
