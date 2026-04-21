import { getDashboardBundle } from "@/lib/data-source";
import { getDatasetBuilderMeta } from "@/lib/dataset-flow";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { Tabs } from "@/components/ui/tabs";

export default async function SnapshotDetailPage({
  params
}: {
  params: Promise<{ snapshotId: string }>;
}) {
  const { snapshotId } = await params;
  const {
    bundle: { evalSuites, routerHandoffs, snapshots, trainingRequests }
  } = await getDashboardBundle();
  const snapshot = snapshots.find((item) => item.id === snapshotId) ?? snapshots[0];

  if (!snapshot) {
    return (
      <EmptyState
        actionHref="/datasets"
        actionLabel="返回数据集"
        description="当前还没有可查看的数据快照。先从训练批次导出第一份数据快照。"
        title="快照不存在"
      />
    );
  }

  const requests = trainingRequests ?? [];
  const suites = evalSuites ?? [];
  const handoffs = routerHandoffs ?? [];
  const relatedRequests = requests.filter((request) => request.datasetSnapshotId === snapshot.id);
  const relatedSuites = suites.filter(
    (suite) =>
      suite.datasetSnapshotId === snapshot.id ||
      relatedRequests.some((request) => request.evalSuiteId === suite.id)
  );
  const requestIds = new Set(relatedRequests.map((request) => request.id));
  const relatedLaunches = handoffs.filter((handoff) =>
    requests.some((request) => requestIds.has(request.id) && (request.handoffIds ?? []).includes(handoff.id))
  );
  const snapshotMeta = getDatasetBuilderMeta(snapshot.builder);

  const nextRecommendation = !relatedRequests.length
    ? {
        title: "先建立训练请求",
        tone: "warning" as const,
        summary: "这份快照已经冻结，但还没有接入训练资产。下一步先确认基座模型、训练 recipe 和日志输出路径。",
        primaryHref: "/training",
        primaryLabel: "进入训练工作区"
      }
    : !relatedSuites.length
      ? {
          title: "补评测资产",
          tone: "info" as const,
          summary: "当前已经有训练请求，但还没有稳定的评测套件。先把这份快照接到固定验证资产，再判断是否进入上线控制面。",
          primaryHref: "/evaluation",
          primaryLabel: "进入评测工作区"
        }
      : !relatedLaunches.length
        ? {
            title: "进入上线控制面",
            tone: "accent" as const,
            summary: "训练和评测资产已经齐了，下一步把评测结论转成放量、保留或回退决策。",
            primaryHref: "/coverage",
            primaryLabel: "查看上线控制面"
          }
        : {
            title: "已接到上线链路",
            tone: "success" as const,
            summary: "这份快照已经串到了训练、评测和上线接替，可以直接查看当前切片是否可执行。",
            primaryHref: "/coverage",
            primaryLabel: "打开上线控制面"
          };

  const progressSteps = [
    {
      title: "来源批次",
      detail: snapshot.cohortName ?? snapshot.cohortId,
      status: "done"
    },
    {
      title: "数据快照",
      detail: `${snapshotMeta.label} · ${snapshot.recordCount} 条记录`,
      status: "done"
    },
    {
      title: "训练请求",
      detail: relatedRequests.length ? `${relatedRequests.length} 个请求已创建` : "还没有关联训练请求",
      status: relatedRequests.length ? "done" : "current"
    },
    {
      title: "评测资产",
      detail: relatedSuites.length ? `${relatedSuites.length} 个评测套件已关联` : "还没有关联评测套件",
      status: relatedSuites.length ? "done" : relatedRequests.length ? "current" : "upcoming"
    },
    {
      title: "上线接替",
      detail: relatedLaunches.length ? `${relatedLaunches.length} 个交接资产已产生` : "还没有进入上线接替",
      status: relatedLaunches.length ? "done" : relatedSuites.length ? "current" : "upcoming"
    }
  ];

  const tabItems = [
    {
      id: "manifest",
      label: "导出清单",
      content: (
        <div className="grid gap-3 md:grid-cols-2">
          {[
            `Taxonomy 版本：${snapshot.taxonomyVersions?.join(", ") || "待补充"}`,
            `时间范围：${snapshot.timeRangeLabel ?? "待补充"}`,
            `切分策略：${snapshot.splitSummary ?? "待补充"}`,
            `批次约束：${snapshot.selectionSummary ?? "待补充"}`,
            `输出路径：${snapshot.outputPath}`
          ].map((line) => (
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={line}>
              {line}
            </div>
          ))}
          <details className="panel-soft rounded-2xl p-4 md:col-span-2">
            <summary className="cursor-pointer text-sm font-medium text-[color:var(--text)]">查看技术明细</summary>
            <div className="mono mt-3 text-xs text-[color:var(--text-soft)]">{snapshot.id}</div>
          </details>
        </div>
      )
    },
    {
      id: "split",
      label: "切分分布",
      content: (
        <div className="grid gap-3 md:grid-cols-3">
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">样本单元：{snapshot.sampleUnit}</div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">记录数：{snapshot.recordCount}</div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">来源批次：{snapshot.cohortName ?? snapshot.cohortId}</div>
        </div>
      )
    },
    {
      id: "preview",
      label: "记录说明",
      content: (
        <div className="space-y-3">
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            这份快照承载 {snapshotMeta.label} 导出类型，当前以 {snapshot.sampleUnit} 为样本单元。
          </div>
          <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]">
            如果要继续训练或评测，优先检查切分策略、批次约束和当前下游资产是否与用途一致。
          </div>
        </div>
      )
    },
    {
      id: "lineage",
      label: "谱系",
      content: (
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">训练请求</div>
            <div className="mt-3 space-y-3">
              {relatedRequests.length ? (
                relatedRequests.map((request) => (
                  <div key={request.id}>
                    <div className="font-medium">{request.title}</div>
                    <div className="mt-1 text-sm text-[color:var(--text-muted)]">{request.summary}</div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-[color:var(--text-muted)]">还没有关联训练请求。</div>
              )}
            </div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">评测套件</div>
            <div className="mt-3 space-y-3">
              {relatedSuites.length ? (
                relatedSuites.map((suite) => (
                  <div key={suite.id}>
                    <div className="font-medium">{suite.title ?? suite.id}</div>
                    <div className="mt-1 text-sm text-[color:var(--text-muted)]">{suite.kind} · {suite.items} 项</div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-[color:var(--text-muted)]">还没有关联评测套件。</div>
              )}
            </div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">上线接替</div>
            <div className="mt-3 space-y-3">
              {relatedLaunches.length ? (
                relatedLaunches.map((handoff) => (
                  <div key={handoff.id}>
                    <div className="font-medium">{handoff.title}</div>
                    <div className="mt-1 text-sm text-[color:var(--text-muted)]">
                      {handoff.trafficScope ?? handoff.sliceLabel ?? handoff.sliceId}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-sm text-[color:var(--text-muted)]">还没有关联上线接替资产。</div>
              )}
            </div>
          </div>
        </div>
      )
    }
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={snapshot.title ?? `${snapshotMeta.label} 数据快照`}
        description="先确认这份冻结快照当前还缺哪一步，再继续接训练、评测或上线控制面；导出清单和技术明细放在后半段查看。"
        primaryAction={<Button href={nextRecommendation.primaryHref} variant="primary">{nextRecommendation.primaryLabel}</Button>}
        secondaryAction={<Button href={`/curation/cohorts/${snapshot.cohortId}`} variant="secondary">返回来源批次</Button>}
      />

      <Card eyebrow="当前去向" title={nextRecommendation.title} strong>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={nextRecommendation.tone}>{nextRecommendation.title}</Badge>
          <Badge tone="info">{snapshotMeta.label}</Badge>
          <Badge tone="neutral">{snapshot.recordCount} 条记录</Badge>
        </div>
        <p className="mt-4 max-w-3xl text-sm leading-6 text-[color:var(--text-muted)]">
          {nextRecommendation.summary}
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">来源批次</div>
            <div className="mt-3 text-xl font-semibold">{snapshot.cohortName ?? snapshot.cohortId}</div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">训练请求</div>
            <div className="mt-3 text-xl font-semibold">{relatedRequests.length}</div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">评测套件</div>
            <div className="mt-3 text-xl font-semibold">{relatedSuites.length}</div>
          </div>
          <div className="panel-soft rounded-2xl p-4">
            <div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">上线接替</div>
            <div className="mt-3 text-xl font-semibold">{relatedLaunches.length}</div>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-3">
          <Button href={nextRecommendation.primaryHref} variant="primary">{nextRecommendation.primaryLabel}</Button>
          <Button href="/datasets" variant="secondary">返回数据集</Button>
          <Button href={relatedRequests.length ? "/training" : "/flows/build-dataset"} variant="ghost">
            {relatedRequests.length ? "查看训练链路" : "查看导出步骤"}
          </Button>
        </div>
      </Card>

      <Card eyebrow="构建进度" title="这份快照离下游还有几步">
        <div className="grid gap-3 xl:grid-cols-5">
          {progressSteps.map((step) => (
            <div
              className={
                step.status === "done"
                  ? "tech-highlight rounded-[1.15rem] p-4"
                  : step.status === "current"
                    ? "rounded-[1.15rem] border border-amber-200 bg-amber-50 p-4"
                    : "panel-soft rounded-[1.15rem] p-4"
              }
              key={step.title}
            >
              <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">{step.title}</div>
              <div className="mt-2 font-medium">{step.detail}</div>
            </div>
          ))}
        </div>
      </Card>

      <Card eyebrow="快照摘要" title={snapshotMeta.label} strong>
        <div className="grid gap-3 md:grid-cols-4">
          <div className="tech-highlight rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">导出类型</div><div className="mt-3 text-xl font-semibold">{snapshotMeta.label}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">样本单元</div><div className="mt-3 text-xl font-semibold">{snapshot.sampleUnit}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">记录数</div><div className="mt-3 text-xl font-semibold">{snapshot.recordCount}</div></div>
          <div className="panel-soft rounded-2xl p-4"><div className="text-xs uppercase tracking-[0.16em] text-[color:var(--text-soft)]">创建时间</div><div className="mt-3 text-xl font-semibold">{snapshot.createdAt}</div></div>
        </div>
      </Card>

      <Card eyebrow="快照内容" title="导出清单与谱系">
        <Tabs active="manifest" items={tabItems} />
      </Card>
    </div>
  );
}
