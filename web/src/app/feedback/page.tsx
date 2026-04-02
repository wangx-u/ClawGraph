import { getDashboardBundle } from "@/lib/data-source";
import { genericStatusLabel, genericStatusTone } from "@/lib/presenters";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";

export default async function FeedbackPage() {
  const {
    bundle: { feedbackItems }
  } = await getDashboardBundle();

  return (
    <div className="space-y-6">
      <PageHeader
        title="回流"
        description="把 fallback、分歧和 verifier fail 的样本重新送回证据复查、监督补标或 cohort refresh，形成闭环。"
        primaryAction={<Button href="/flows/review-feedback" variant="primary">处理回流流程</Button>}
        secondaryAction={<Button href="/sessions" variant="secondary">打开会话收件箱</Button>}
      />

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card eyebrow="回流队列" title="开放闭环事项" strong>
          <DataTable
            headers={["回流单", "来源", "目标", "原因", "切片", "状态"]}
            rows={feedbackItems.map((item) => [
              <span className="mono text-xs text-[color:var(--text-soft)]" key={`${item.id}-id`}>{item.id}</span>,
              item.source,
              <span className="mono text-xs text-[color:var(--text-soft)]" key={`${item.id}-target`}>{item.targetRef}</span>,
              item.reason,
              item.sliceId,
              <Badge key={`${item.id}-status`} tone={genericStatusTone(item.status)}>{genericStatusLabel(item.status)}</Badge>
            ])}
          />
        </Card>

        <Card eyebrow="分流动作" title="将选中项送往">
          <div className="space-y-3">
            {[
              ["送回会话收件箱", "/sessions"],
              ["送到监督模块", "/supervision"],
              ["送到策展模块", "/curation/candidates"],
              ["触发 Cohort Refresh", "/curation/cohorts/cohort_train_001"]
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
