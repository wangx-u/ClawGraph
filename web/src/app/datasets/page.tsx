import { getDashboardBundle } from "@/lib/data-source";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";
import { DatasetWorkspace } from "@/components/dashboard/dataset-workspace";

export default async function DatasetsPage() {
  const {
    bundle: { evalSuites, modelCandidates, readinessRows, routerHandoffs, snapshots, trainingRequests }
  } = await getDashboardBundle();
  const readyBuilders = readinessRows.filter((row) => row.ready).length;
  const waitingForFirstSnapshot = readinessRows.filter(
    (row) => row.ready && !snapshots.some((snapshot) => snapshot.builder === row.builder)
  ).length;
  const linkedTrainingRequests = (trainingRequests ?? []).filter((request) => request.datasetSnapshotId).length;
  const linkedEvalSuites = (evalSuites ?? []).filter((suite) => suite.datasetSnapshotId).length;

  if (!readinessRows.length && !snapshots.length) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="数据集"
          description="当前真实数据源里还没有可导出的导出类型或快照。先完成策展、监督或首轮数据准备，再回来查看。"
          primaryAction={<Button href="/curation/candidates" variant="primary">返回策展</Button>}
          secondaryAction={<Button href="/flows/build-dataset" variant="secondary">查看导出流程</Button>}
        />
        <EmptyState
          actionHref="/curation/candidates"
          actionLabel="打开候选池"
          description="当 ClawGraph store 中出现已就绪导出类型或历史数据快照后，这里会自动切换成高保真工作区。"
          title="还没有数据集资产"
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="数据集"
        description="先按数据快照谱系查看批次、快照、训练请求、评测和上线接替的关系，再回看导出就绪度和待导出队列。"
        primaryAction={<Button href="/flows/build-dataset" variant="primary">导出快照</Button>}
        secondaryAction={<Button href="/curation/candidates" variant="secondary">返回策展</Button>}
      />

      <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-4">
        <div className="surface-strong rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">已冻结数据快照</div>
          <div className="mt-3 text-3xl font-semibold">{snapshots.length}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">已关联训练请求</div>
          <div className="mt-3 text-3xl font-semibold">{linkedTrainingRequests}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">已关联评测资产</div>
          <div className="mt-3 text-3xl font-semibold">{linkedEvalSuites}</div>
        </div>
        <div className="surface rounded-[1.35rem] p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">待首版快照的已就绪导出类型</div>
          <div className="mt-3 text-3xl font-semibold">{Math.max(waitingForFirstSnapshot, readyBuilders - snapshots.length)}</div>
        </div>
      </div>

      <DatasetWorkspace
        evalSuites={evalSuites ?? []}
        modelCandidates={modelCandidates ?? []}
        readinessRows={readinessRows}
        routerHandoffs={routerHandoffs ?? []}
        snapshots={snapshots}
        trainingRequests={trainingRequests ?? []}
      />
    </div>
  );
}
