import { getDashboardBundle } from "@/lib/data-source";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";

export default async function FeedbackPage() {
  const {
    bundle: { cohorts, feedbackItems }
  } = await getDashboardBundle();
  const cohortHref = cohorts[0] ? `/curation/cohorts/${cohorts[0].id}` : "/curation/candidates";
  const queuedCount = feedbackItems.filter((item) => item.status === "queued").length;
  const reviewedCount = feedbackItems.filter((item) => item.status === "reviewed").length;
  const resolvedCount = feedbackItems.filter((item) => item.status === "resolved").length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="人工复核"
        description="把低置信、失败和分歧样本送回复查、数据准备或数据筛选，形成可追溯的闭环。"
        primaryAction={<Button href="/flows/review-feedback" variant="primary">处理回流流程</Button>}
        secondaryAction={<Button href="/sessions" variant="secondary">打开会话收件箱</Button>}
      />

      <div className="grid gap-4 md:grid-cols-3">
        <Card eyebrow="待处理" title={String(queuedCount)}>还需要人工决定下一步。</Card>
        <Card eyebrow="已人工确认" title={String(reviewedCount)}>已经确认过，但还未正式关闭。</Card>
        <Card eyebrow="已关闭" title={String(resolvedCount)}>已完成处理，不再阻塞当前流程。</Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card eyebrow="回流队列" title="开放闭环事项" strong>
          <DataTable
            headers={["回流单", "来源", "目标", "原因", "切片", "状态", "说明"]}
            rows={feedbackItems.map((item) => [
              <span className="mono text-xs text-[color:var(--text-soft)]" key={`${item.id}-id`}>{item.id}</span>,
              item.source,
              <span className="mono text-xs text-[color:var(--text-soft)]" key={`${item.id}-target`}>{item.targetRef}</span>,
              item.reason,
              item.sliceId,
              <Badge key={`${item.id}-status`} tone={genericStatusTone(item.status)}>{genericStatusLabel(item.status)}</Badge>,
              item.resolutionNote ?? item.reviewer ?? "等待处理"
            ])}
          />
        </Card>

        <Card eyebrow="分流动作" title="将选中项送往">
          <div className="space-y-3">
            {[
              ["送回会话收件箱", "/sessions"],
              ["送到数据准备页面", "/supervision"],
              ["送到数据筛选页面", "/curation/candidates"],
              ["查看当前 Cohort", cohortHref]
            ].map(([label, href]) => (
              <Button className="w-full justify-start" href={href} key={label} variant="secondary">
                {label}
              </Button>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
