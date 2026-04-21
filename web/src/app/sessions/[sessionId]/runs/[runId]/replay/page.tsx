import { createHash } from "node:crypto";
import { getDashboardBundle } from "@/lib/data-source";
import {
  evidenceLabel,
  evidenceDetail,
  genericStatusLabel,
  genericStatusTone,
  outcomeLabel,
  outcomeTone,
  requestActorLabel,
  shortId,
  workflowStageTone
} from "@/lib/presenters";
import type { ReplayStep } from "@/lib/types";
import {
  bootstrapReplayGovernance,
  confirmRunByHuman,
  syncRunFeedbackQueue
} from "@/app/feedback/actions";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";

type GateState = "pass" | "attention" | "blocked";

function gateTone(state: GateState) {
  if (state === "pass") {
    return "success";
  }
  if (state === "attention") {
    return "warning";
  }
  return "danger";
}

function gateLabel(state: GateState) {
  if (state === "pass") {
    return "通过";
  }
  if (state === "attention") {
    return "待处理";
  }
  return "阻塞";
}

function strongestGateState(states: GateState[]): GateState {
  if (states.includes("blocked")) {
    return "blocked";
  }
  if (states.includes("attention")) {
    return "attention";
  }
  return "pass";
}

function scoreLabel(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "未提供";
  }
  return `${(value * 100).toFixed(1)}%`;
}

function diffSummaryLabel(diffSummary: {
  inserts?: number;
  updates?: number;
  deletes?: number;
} | null | undefined) {
  if (!diffSummary) {
    return "未提供";
  }
  const inserts = diffSummary.inserts ?? 0;
  const updates = diffSummary.updates ?? 0;
  const deletes = diffSummary.deletes ?? 0;
  return `+${inserts} / ~${updates} / -${deletes}`;
}

function slug(value: string) {
  const normalized = value.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return normalized || "unknown";
}

function deriveSliceId(
  taskFamily: string | null | undefined,
  taskType: string | null | undefined,
  taxonomyVersion: string | null | undefined
) {
  if (!taskFamily || !taskType || !taxonomyVersion) {
    return null;
  }
  const digest = createHash("sha1")
    .update(`${taskFamily}|${taskType}|${taxonomyVersion}`)
    .digest("hex")
    .slice(0, 8);
  return `slice.${slug(taskFamily)}.${slug(taskType)}.${digest}`;
}

export default async function ReplayPage({
  params
}: {
  params: Promise<{ sessionId: string; runId: string }>;
}) {
  const { sessionId, runId } = await params;
  const {
    bundle: { feedbackItems, replayRecords, sessions },
    meta
  } = await getDashboardBundle();
  const replay = replayRecords.find((item) => item.sessionId === sessionId && item.runId === runId) ?? replayRecords[0] ?? null;
  const session = replay ? sessions.find((item) => item.id === replay.sessionId) ?? sessions[0] ?? null : null;
  const run = replay && session ? session.runs.find((item) => item.id === replay.runId) ?? session.runs[0] ?? null : null;

  if (!replay || !session || !run) {
    return (
      <EmptyState
        actionHref="/sessions"
        actionLabel="返回会话收件箱"
        description="当前没有可回放的运行数据，先确认 session 是否已采集并写入 store。"
        title="回放数据不存在"
      />
    );
  }

  const artifactCount = run.artifactCount ?? replay.requests.reduce((sum, item) => sum + item.artifactCount, 0);
  const builderBadges = run.readyBuilders ?? [];
  const runBlockers = run.readinessBlockers ?? run.blockers ?? [];
  const timelineSteps: ReplayStep[] =
    replay.timelineSteps ?? replay.timeline.map((label) => ({ label }));
  const declaredBranchCount = replay.branches.filter((branch) => branch.source === "declared").length;
  const inferredBranchCount = replay.branches.length - declaredBranchCount;
  const requestClosureState: GateState = run.openCount === 0 ? "pass" : "blocked";
  const trajectoryState: GateState =
    run.declaredRatio >= 0.75 ? "pass" : run.declaredRatio >= 0.5 ? "attention" : "blocked";
  const semanticState: GateState =
    run.evidenceLevel === "E2" ? "pass" : run.evidenceLevel === "E1" ? "attention" : "blocked";
  const judgeState: GateState =
    run.reviewStatus === "clean" || run.reviewStatus === "human"
      ? "pass"
      : run.reviewStatus === "review"
        ? "attention"
        : "blocked";
  const datasetEligibilityState: GateState =
    builderBadges.length && !runBlockers.length && requestClosureState === "pass" && trajectoryState !== "blocked" && semanticState !== "blocked" && judgeState !== "blocked"
      ? "pass"
      : builderBadges.length || runBlockers.length
        ? "attention"
        : "blocked";
  const canEnterDataset = datasetEligibilityState === "pass";
  const relatedFeedbackItems = feedbackItems.filter((item) => {
    if (item.runId && item.runId === run.id) {
      return true;
    }
    if (item.sessionId && item.sessionId === session.id && (!item.runId || item.runId === run.id)) {
      return true;
    }
    if (item.targetRef === `run:${run.id}`) {
      return true;
    }
    return replay.branches.some((branch) => item.targetRef === `branch:${branch.id}`);
  });
  const openFeedbackItems = relatedFeedbackItems.filter((item) => item.status !== "resolved");
  const canMutate = Boolean(meta.supportsMutations);
  const canRunLocalReplayAutomation = canMutate && meta.provider === "local-store";
  const resolvedSliceId = run.sliceId ?? replay.sliceId ?? null;
  const derivedSliceId = deriveSliceId(run.taskFamily, run.taskType, run.taxonomyVersion);
  const displaySliceId = resolvedSliceId ?? derivedSliceId;
  const canHumanOverrideIntoDataset =
    canMutate &&
    builderBadges.length > 0 &&
    requestClosureState !== "blocked" &&
    trajectoryState !== "blocked" &&
    semanticState !== "blocked" &&
    judgeState !== "pass";
  const canBootstrapReviewQueue =
    canRunLocalReplayAutomation &&
    !resolvedSliceId &&
    Boolean(run.taskFamily && run.taskType && run.taxonomyVersion);
  const needsBootstrapReviewQueue =
    !resolvedSliceId && Boolean(run.taskFamily && run.taskType && run.taxonomyVersion);
  const canSyncReviewQueue =
    canRunLocalReplayAutomation &&
    Boolean(resolvedSliceId) &&
    openFeedbackItems.length === 0 &&
    judgeState !== "pass";
  const needsSyncReviewQueue =
    Boolean(resolvedSliceId) && openFeedbackItems.length === 0 && judgeState !== "pass";
  const sliceRegistrationState: GateState = resolvedSliceId
    ? "pass"
    : derivedSliceId
      ? "attention"
      : "blocked";
  const feedbackQueueState: GateState = openFeedbackItems.length
    ? "pass"
    : judgeState === "pass"
      ? "pass"
      : resolvedSliceId
        ? "attention"
        : "blocked";
  const entrySourceLabel = openFeedbackItems.length
    ? "这条运行带着复核事项进入回放"
    : judgeState !== "pass"
      ? "这条运行正在等待人工确认"
      : requestClosureState === "blocked" || trajectoryState !== "pass"
        ? "这条运行需要先确认轨迹结构"
        : canEnterDataset
          ? "这条运行正在做数据集准入复查"
          : "这条运行仍在等待下一步分流";
  const primaryDestination =
    canEnterDataset
      ? {
          href: "/datasets",
          label: "继续数据集生产",
          detail: "这次回放已经满足数据集准入，下一步去确认来源批次和导出类型。"
        }
      : requestClosureState === "blocked" || trajectoryState === "blocked"
        ? {
            href: `/sessions/${session.id}`,
            label: "回会话继续分诊",
            detail: "先处理 open span、推断分支和结构缺口，再回来做最终确认。"
          }
        : semanticState !== "pass" || judgeState !== "pass" || runBlockers.length
          ? {
              href: "/supervision",
              label: "回自动判断补证据",
              detail: "这条运行当前更适合回到自动判断和监督页补齐标签、语义和 builder readiness。"
            }
          : openFeedbackItems.length
            ? {
                href: "/feedback",
                label: "进入人工复核队列",
                detail: "先把相关复核项处理完，再决定是否继续入池或送回上游。"
              }
            : {
                href: `/sessions/${session.id}`,
                label: "返回会话",
            detail: "当前没有直接可推进的下游动作，先回会话继续观察上下文。"
              };
  const auxiliaryDestination =
    openFeedbackItems.length && primaryDestination.href !== "/feedback"
      ? {
          href: "/feedback",
          label: "查看复核队列"
        }
      : primaryDestination.href !== "/supervision"
        ? {
            href: "/supervision",
            label: "回自动判断"
          }
        : {
            href: `/sessions/${session.id}`,
            label: "返回会话上下文"
          };
  const reviewChecklist = [
    {
      label: "Step 1 先看结构是否可信",
      state: strongestGateState([requestClosureState, trajectoryState]),
      detail:
        requestClosureState === "pass" && trajectoryState === "pass"
          ? `请求已闭环，显式轨迹覆盖 ${Math.round(run.declaredRatio * 100)}%，结构可以继续作为确认依据。`
          : requestClosureState === "blocked"
            ? `${run.openCount} 个请求还未闭环，先确认执行终态，再继续判断。`
            : `当前仍有 ${inferredBranchCount} 个推断分支，先确认它们是否足够可信。`
    },
    {
      label: "Step 2 再看判断是否可接受",
      state: strongestGateState([semanticState, judgeState]),
      detail:
        semanticState === "pass" && judgeState === "pass"
          ? "语义证据和自动判断都已经稳定，可以把这次回放当作准入依据。"
          : run.reviewReasons?.length
            ? `先确认这些判断理由是否成立：${run.reviewReasons.slice(0, 2).join("、")}。`
            : evidenceDetail(run.evidenceLevel)
    },
    {
      label: "Step 3 最后决定去向",
      state: datasetEligibilityState,
      detail: primaryDestination.detail
    }
  ];
  const relatedFeedbackSummary = openFeedbackItems.length
    ? `${openFeedbackItems.length} 个待处理复核项正在引用这条运行或它的分支。`
    : judgeState !== "pass"
      ? "当前没有单独挂起的复核项，但这条运行本身仍在等待人工确认。"
      : "当前没有额外复核项，可以直接按 gate 结果进入下一步。";
  const gateChecks = [
    {
      label: "请求闭环",
      state: requestClosureState,
      detail:
        run.openCount === 0
          ? `全部 ${replay.requests.length} 个请求已闭合，可以进入后续判断。`
          : `${run.openCount} 个 open span 仍未闭合，先补齐执行终态。`
    },
    {
      label: "轨迹结构",
      state: trajectoryState,
      detail:
        run.declaredRatio >= 0.75
          ? `显式轨迹覆盖 ${Math.round(run.declaredRatio * 100)}%，结构可信。`
          : `显式轨迹覆盖 ${Math.round(run.declaredRatio * 100)}%，其中 ${inferredBranchCount} 个分支仍依赖推断。`
    },
    {
      label: "语义证据",
      state: semanticState,
      detail:
        run.evidenceLevel === "E2"
          ? `已达到 ${evidenceLabel(run.evidenceLevel)}，${artifactCount} 条判断记录足够支持后续筛选。`
          : run.evidenceLevel === "E1"
            ? `当前只有 ${evidenceLabel(run.evidenceLevel)}，仍建议补更多关键语义。`
            : `当前只有 ${evidenceLabel(run.evidenceLevel)}，还不能稳定进入候选池。`
    },
    {
      label: "自动判断",
      state: judgeState,
      detail:
        run.reviewStatus === "clean" || run.reviewStatus === "human"
          ? `当前复核状态为 ${run.reviewStatus === "human" ? "已人工确认" : "已通过自动检查"}。`
          : run.reviewReasons?.length
            ? `当前仍需处理：${run.reviewReasons.slice(0, 2).join("、")}。`
            : "自动判断已发现风险，仍需补充确认。"
    },
    {
      label: "数据集准入",
      state: datasetEligibilityState,
      detail: canEnterDataset
        ? `已匹配 ${builderBadges.join("、")}，可继续进入数据批次 / 数据快照。`
        : builderBadges.length
          ? `已有 builder 候选，但仍受以下条件影响：${runBlockers.slice(0, 2).join("、") || "还需复核当前判断结果"}。`
          : "当前没有可用 builder，先补齐标签、判断或人工复核。"
    }
  ];
  const operationChecks = [
    {
      label: "切片注册",
      state: sliceRegistrationState,
      detail: resolvedSliceId
        ? `当前运行已经落到 slice ${resolvedSliceId}，后续复核、cohort 和评测都可以沿这个主键继续。`
        : derivedSliceId
          ? `数据库里还没有 slice 记录，但已经能从 taxonomy 推导出 ${derivedSliceId}。先注册它，后续复核队列才能自动生成。`
          : "当前 annotation 还不够完整，无法自动注册 slice。先补 task family / type / taxonomy version。"
    },
    {
      label: "复核队列",
      state: feedbackQueueState,
      detail: openFeedbackItems.length
        ? `当前已有 ${openFeedbackItems.length} 个复核项引用这条运行，可以直接进入人工复核队列。`
        : judgeState === "pass"
          ? "这条运行当前没有待生成的复核项，人工确认已经完成。"
          : resolvedSliceId
            ? "当前仍待复核，但 feedback queue 还是空的。建议直接从 slice review 生成复核项。"
            : "先完成 slice 注册，再从 slice review 自动生成 feedback queue。"
    },
    {
      label: "数据集生产",
      state: datasetEligibilityState,
      detail: canEnterDataset
        ? "Gate 已通过，可以直接进入数据集 builder、冻结 cohort 或导出 snapshot。"
        : "当前还没到数据生产阶段。先把结构、判断或复核入口补齐。"
    }
  ];
  const primaryGateMessage = canEnterDataset
    ? "这条运行已经满足数据集生产的准入条件。"
    : "这条运行还不能直接进入数据集生产，需要先处理下面的 gate。";

  return (
    <div className="space-y-6">
      <PageHeader
        title={replay.title ? `回放 ${replay.title}` : `回放 ${shortId(replay.runId)}`}
        description="按执行顺序还原一个真实运行的请求、分支和语义事件，用于判断它现在卡在哪一步，以及下一步要补什么。"
        primaryAction={<Button href={primaryDestination.href} variant="primary">{primaryDestination.label}</Button>}
        secondaryAction={
          <Button href={`/sessions/${session.id}`} variant="secondary">
            返回会话
          </Button>
        }
      />

      <Card eyebrow="待用户回放确认" title={entrySourceLabel} strong>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={gateTone(datasetEligibilityState)}>
            {canEnterDataset ? "准入已通过" : "仍待人工确认"}
          </Badge>
          {openFeedbackItems.length ? (
            <Badge tone="warning">{openFeedbackItems.length} 个相关复核项</Badge>
          ) : null}
          <Badge tone={workflowStageTone(run.stage)}>{run.stageLabel ?? evidenceLabel(run.evidenceLevel)}</Badge>
        </div>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-[color:var(--text-muted)]">
          {relatedFeedbackSummary} 这页的目标不是再看一遍日志，而是先确认结构、判断和去向，再把这条运行送到正确的下一站。
        </p>
        <div className="mt-4 grid gap-3 xl:grid-cols-3">
          {reviewChecklist.map((item) => (
            <div className="panel-soft rounded-[1.1rem] p-4" key={item.label}>
              <div className="flex items-start justify-between gap-3">
                <div className="text-sm font-medium">{item.label}</div>
                <Badge tone={gateTone(item.state)}>{gateLabel(item.state)}</Badge>
              </div>
              <div className="mt-3 text-sm leading-6 text-[color:var(--text-muted)]">{item.detail}</div>
            </div>
          ))}
        </div>
        {openFeedbackItems.length ? (
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            {openFeedbackItems.map((item) => (
              <div className="rounded-[1.1rem] border border-amber-200 bg-amber-50 p-4" key={item.id}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-amber-900">{item.targetLabel ?? item.targetRef}</div>
                    <div className="mt-2 text-sm leading-6 text-amber-800">{item.reason}</div>
                  </div>
                  <Badge tone={genericStatusTone(item.status)}>{genericStatusLabel(item.status)}</Badge>
                </div>
              </div>
            ))}
          </div>
        ) : null}
        <div className="mt-5 flex flex-wrap gap-3">
          {canHumanOverrideIntoDataset ? (
            <form action={confirmRunByHuman}>
              <input name="sessionId" type="hidden" value={session.id} />
              <input name="runId" type="hidden" value={run.id} />
              {openFeedbackItems[0] ? (
                <input name="feedbackId" type="hidden" value={openFeedbackItems[0].id} />
              ) : null}
              <Button type="submit" variant="primary">人工确认并继续入池</Button>
            </form>
          ) : (
            <Button href={primaryDestination.href} variant="primary">{primaryDestination.label}</Button>
          )}
          {canHumanOverrideIntoDataset ? (
            <Button href={primaryDestination.href} variant="secondary">{primaryDestination.label}</Button>
          ) : null}
          <Button href={auxiliaryDestination.href} variant="secondary">
            {auxiliaryDestination.label}
          </Button>
          <Button href={`/sessions/${session.id}`} variant="ghost">返回会话上下文</Button>
        </div>
      </Card>

      <Card eyebrow="真实任务上下文" title="这次回放对应哪条任务以及当前评分">
        <div className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <div className="panel-soft rounded-[1.1rem] p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">任务指令</div>
            <div className="mt-3 text-sm leading-6 text-[color:var(--text-muted)]">
              {replay.prompt ?? "当前 store 没有记录原始 prompt。"}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {replay.suiteName ? <Badge tone="accent">{replay.suiteName}</Badge> : null}
              {replay.testName ? <Badge tone="info">{replay.testName}</Badge> : null}
              {run.taskFamily && run.taskType ? (
                <Badge tone="neutral">{`${run.taskFamily} / ${run.taskType}`}</Badge>
              ) : null}
              {run.taxonomyVersion ? <Badge tone="neutral">{run.taxonomyVersion}</Badge> : null}
              {displaySliceId ? (
                <Badge tone={resolvedSliceId ? "success" : "warning"}>
                  {resolvedSliceId ? `Slice ${displaySliceId}` : `待注册 ${displaySliceId}`}
                </Badge>
              ) : null}
            </div>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">评测得分</div>
              <div className="mt-3 text-2xl font-semibold">{scoreLabel(replay.scoreValue)}</div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                {replay.scorePassed === null
                  ? "当前没有 score artifact。"
                  : replay.scorePassed
                    ? "这次对比已通过 verifier。"
                    : "这次对比没有通过 verifier，需要人工复核差异。"}
              </div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">Diff 摘要</div>
              <div className="mt-3 text-2xl font-semibold">{diffSummaryLabel(replay.diffSummary)}</div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                {replay.verifierName
                  ? `${replay.verifierName} · confidence ${scoreLabel(replay.qualityConfidence)}`
                  : "当前没有 verifier 元数据。"}
              </div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">环境</div>
              <div className="mt-3 text-sm font-medium">{replay.environmentId ?? "未记录环境 ID"}</div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                复现回放时应优先确认这条运行是否仍在同一个沙箱或租户上下文中。
              </div>
            </div>
            <div className="panel-soft rounded-[1.1rem] p-4">
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">判分来源</div>
              <div className="mt-3 text-sm font-medium">
                {replay.verifierName ?? "未记录 verifier"}
              </div>
              <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                {typeof replay.verifierScore === "number"
                  ? `verifier score ${scoreLabel(replay.verifierScore)}`
                  : "当前没有 verifier score。"}
              </div>
            </div>
          </div>
        </div>
      </Card>

      <Card eyebrow="自动化入口" title="当前页面还缺哪些 Store 操作">
        <div className="grid gap-3 xl:grid-cols-3">
          {operationChecks.map((item) => (
            <div className="panel-soft rounded-[1.1rem] p-4" key={item.label}>
              <div className="flex items-start justify-between gap-3">
                <div className="text-sm font-medium">{item.label}</div>
                <Badge tone={gateTone(item.state)}>{gateLabel(item.state)}</Badge>
              </div>
              <div className="mt-3 text-sm leading-6 text-[color:var(--text-muted)]">{item.detail}</div>
            </div>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          {canBootstrapReviewQueue ? (
            <form action={bootstrapReplayGovernance}>
              <input name="sessionId" type="hidden" value={session.id} />
              <input name="runId" type="hidden" value={run.id} />
              <Button type="submit" variant="primary">注册 Slice 并生成复核队列</Button>
            </form>
          ) : null}
          {canSyncReviewQueue && resolvedSliceId ? (
            <form action={syncRunFeedbackQueue}>
              <input name="sliceId" type="hidden" value={resolvedSliceId} />
              <input name="sessionId" type="hidden" value={session.id} />
              <input name="runId" type="hidden" value={run.id} />
              <Button type="submit" variant="primary">从 Slice Review 生成复核项</Button>
            </form>
          ) : null}
          {openFeedbackItems.length ? (
            <Button href="/feedback" variant="secondary">进入人工复核队列</Button>
          ) : null}
          <Button href={canEnterDataset ? "/datasets" : "/supervision"} variant="secondary">
            {canEnterDataset ? "去数据集生产" : "回自动判断补条件"}
          </Button>
          <Button href={`/sessions/${session.id}`} variant="ghost">返回会话上下文</Button>
        </div>
        {!canRunLocalReplayAutomation && (needsBootstrapReviewQueue || needsSyncReviewQueue) ? (
          <div className="mt-4 text-sm text-[color:var(--text-muted)]">
            当前页面不是本地 Store 模式，暂时无法直接执行写操作。请切到本地 Store 或通过控制面 API 完成这些动作。
          </div>
        ) : null}
      </Card>

      <Card
        action={
          <Button href={canEnterDataset ? "/datasets" : "/supervision"} variant="primary">
            {canEnterDataset ? "继续数据集生产" : "先处理 Gate"}
          </Button>
        }
        eyebrow="Trajectory Gate"
        title={canEnterDataset ? "详细 Gate 结果：已满足数据集准入" : "详细 Gate 结果：尚未满足数据集准入"}
        strong
      >
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={canEnterDataset ? "success" : "warning"}>
            {canEnterDataset ? "可进入数据集" : "仍有阻塞"}
          </Badge>
          <Badge tone={workflowStageTone(run.stage)}>{run.stageLabel ?? evidenceLabel(run.evidenceLevel)}</Badge>
          <Badge tone={outcomeTone(run.outcome)}>{outcomeLabel(run.outcome)}</Badge>
        </div>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-[color:var(--text-muted)]">{primaryGateMessage}</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          {gateChecks.map((check) => (
            <div className="panel-soft rounded-[1.1rem] p-4" key={check.label}>
              <div className="flex items-start justify-between gap-3">
                <div className="text-sm font-medium">{check.label}</div>
                <Badge tone={gateTone(check.state)}>{gateLabel(check.state)}</Badge>
              </div>
              <div className="mt-3 text-sm leading-6 text-[color:var(--text-muted)]">{check.detail}</div>
            </div>
          ))}
        </div>
        <div className="mt-4 grid gap-3 lg:grid-cols-3">
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            当前阶段：{run.stageLabel ?? evidenceLabel(run.evidenceLevel)}。{run.stageDetail ?? "先确认这次运行是否已经具备稳定标签。"}
          </div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            可用 Builder：{builderBadges.length ? builderBadges.join("、") : "暂时没有，需要继续补监督。"}
          </div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            下一步：{run.nextAction ?? "回到补标签或样本治理页面继续处理。"}
          </div>
        </div>
        {runBlockers.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {runBlockers.slice(0, 4).map((item) => (
              <Badge key={item} tone="warning">
                {item}
              </Badge>
            ))}
          </div>
        ) : null}
      </Card>

      <Card eyebrow="回放摘要" title={replay.title ?? run.title ?? shortId(replay.runId)} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">结果</div><div className="mt-3 text-2xl font-semibold">{outcomeLabel(run.outcome)}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">请求数</div><div className="mt-3 text-2xl font-semibold">{replay.requests.length}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">分支数</div><div className="mt-3 text-2xl font-semibold">{replay.branches.length}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">判断记录</div><div className="mt-3 text-2xl font-semibold">{artifactCount}</div></div>
        </div>
        <div className="mt-4 text-sm text-[color:var(--text-muted)]">
          {replay.summary ?? run.summary ?? "这次回放展示了一次完整运行的主要步骤、分支和后续动作。"}
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Badge tone={outcomeTone(run.outcome)}>{outcomeLabel(run.outcome)}</Badge>
          <Badge tone="info">{run.avgLatency}</Badge>
          <Badge tone={workflowStageTone(run.stage)}>{run.stageLabel ?? evidenceLabel(run.evidenceLevel)}</Badge>
          <Badge tone="accent">{session.title ?? `会话 ${shortId(replay.sessionId)}`}</Badge>
        </div>
      </Card>

      <Card eyebrow="时间线" title="执行顺序">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {timelineSteps.map((step, index) => (
            <div className="panel-soft rounded-[1.1rem] p-4" key={`${index}-${step.label}`}>
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">步骤 {index + 1}</div>
              <div className="mt-3 text-sm font-medium">{step.label}</div>
              {step.detail ? (
                <div className="mt-2 text-sm leading-6 text-[color:var(--text-muted)]">{step.detail}</div>
              ) : null}
            </div>
          ))}
        </div>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <Card eyebrow="关键分支" title="这次运行如何拆分处理">
          <div className="space-y-3">
            {replay.branches.map((branch) => (
              <div className="panel-soft rounded-[1.1rem] p-4" key={branch.id}>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-medium">{branch.title ?? branch.type}</div>
                    <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                      {branch.summary ?? `${branch.requestCount ?? branch.requestIds.length} 个步骤`}
                    </div>
                    <div className="mono mt-2 text-xs text-[color:var(--text-soft)]">分支 {shortId(branch.id)}</div>
                  </div>
                  <Badge tone={genericStatusTone(branch.status)}>{genericStatusLabel(branch.status)}</Badge>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card eyebrow="请求步骤" title="每一步做了什么以及实际执行了什么">
          <DataTable
            headers={["步骤类型", "执行者", "接口 / 工具", "模型意图", "实际动作", "结果", "状态码", "延迟", "判断记录"]}
            rows={replay.requests.map((request) => [
              <div key={`${request.id}-id`}>
                <div className="font-medium">{request.stepType ?? request.pathLabel ?? "请求步骤"}</div>
                <div className="mono text-xs text-[color:var(--text-soft)]">{shortId(request.id)}</div>
              </div>,
              requestActorLabel(request.actor),
              <div key={`${request.id}-path`}>
                <div>{request.pathLabel ?? request.path}</div>
                {request.toolName ? (
                  <div className="mt-1 text-xs font-medium text-[color:var(--text)]">
                    工具 {request.toolName}
                  </div>
                ) : null}
                <div className="mono text-xs text-[color:var(--text-soft)]">{request.path}</div>
              </div>,
              <div className="space-y-2" key={`${request.id}-assistant`}>
                <div>{request.assistantMessage ?? request.summary ?? "本步没有补充摘要。"}</div>
                {request.assistantMessage && request.summary && request.summary !== request.assistantMessage ? (
                  <div className="text-xs text-[color:var(--text-soft)]">{request.summary}</div>
                ) : null}
              </div>,
              <div className="space-y-2" key={`${request.id}-command`}>
                {request.toolCommand ? (
                  <div className="mono max-w-xl whitespace-pre-wrap break-all rounded-2xl bg-slate-950/95 p-3 text-xs text-slate-100">
                    {request.toolCommand}
                  </div>
                ) : (
                  <div className="text-sm text-[color:var(--text-muted)]">这一步没有额外工具调用。</div>
                )}
              </div>,
              <Badge key={`${request.id}-outcome`} tone={outcomeTone(request.outcome)}>{outcomeLabel(request.outcome)}</Badge>,
              request.status,
              request.latency,
              request.artifactCount
            ])}
          />
        </Card>
      </div>
    </div>
  );
}
