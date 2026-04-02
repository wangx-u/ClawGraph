import { getDashboardBundle } from "@/lib/data-source";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";

export default async function SupervisionPage() {
  const {
    bundle: { artifacts }
  } = await getDashboardBundle();

  return (
    <div className="space-y-6">
      <PageHeader
        title="监督"
        description="在不改写底层事实的前提下管理 bootstrap artifacts、人工监督信号和语义覆盖，支撑后续导出与评测。"
        primaryAction={<Button href="/flows/build-dataset" variant="primary">执行 Bootstrap</Button>}
        secondaryAction={<Button href="/sessions/sess_123/runs/run_capture_1/replay" variant="secondary">返回回放</Button>}
      />

      <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
        <Card eyebrow="Bootstrap 模板" title="内建监督模板" strong>
          <div className="space-y-3">
            {[
              "openclaw-defaults",
              "request-outcome-scores",
              "branch-outcome-preference",
              "e1-annotations"
            ].map((template) => (
              <div className="panel-soft rounded-2xl p-4" key={template}>
                <div className="font-medium">{template}</div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">
                  作为可重复执行的监督预处理步骤，在导出或人工复核前统一落一遍。
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card eyebrow="现有监督" title="Artifacts 与治理状态">
          <DataTable
            headers={["Artifact", "类型", "目标", "生产者", "状态", "置信度", "版本"]}
            rows={artifacts.map((artifact) => [
              <span className="mono text-xs text-[color:var(--text-soft)]" key={`${artifact.id}-id`}>{artifact.id}</span>,
              artifact.type,
              <span className="mono text-xs text-[color:var(--text-soft)]" key={`${artifact.id}-target`}>{artifact.targetRef}</span>,
              artifact.producer,
              <Badge key={`${artifact.id}-status`} tone={genericStatusTone(artifact.status)}>{genericStatusLabel(artifact.status)}</Badge>,
              artifact.confidence,
              artifact.version
            ])}
          />
        </Card>
      </div>

      <Card eyebrow="建议动作" title="监督动作建议">
        <div className="grid gap-3 md:grid-cols-3">
          {[
            "优先给 E0 / E1 的运行补 e1 annotations。",
            "只有在 replay 里确认分支结构正确后，再补 branch-level preference。",
            "每一次 artifact 或 semantic write 都要显式记录 producer 与 version。"
          ].map((item) => (
            <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={item}>
              {item}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
