import { getDashboardBundle } from "@/lib/data-source";
import { Button } from "@/components/ui/button";
import { SessionInboxWorkspace } from "@/components/dashboard/session-inbox-workspace";
import { EmptyState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/ui/page-header";

export default async function SessionsPage() {
  const {
    bundle: { sessions }
  } = await getDashboardBundle();
  const selected = sessions[0];

  if (!selected) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="会话收件箱"
          description="当前真实数据源里还没有可分诊会话。先接入 Runtime 或写入首批数据，再回来查看。"
          primaryAction={<Button href="/access" variant="primary">去接入 Runtime</Button>}
          secondaryAction={<Button href="/flows/connect-runtime" variant="secondary">查看接入流程</Button>}
        />
        <EmptyState
          actionHref="/access"
          actionLabel="打开接入面板"
          description="当 ClawGraph store 中出现第一条会话后，这里会自动切换成可交互的会话工作区。"
          title="还没有会话数据"
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="会话收件箱"
        description="先对新采集的真实会话做结构化分诊，再决定它应该进入回放、监督补标还是后续数据集流程。"
        primaryAction={<Button href={`/sessions/${selected.id}`} variant="primary">复查最新会话</Button>}
        secondaryAction={<Button href="/supervision" variant="secondary">进入自动判断</Button>}
      />

      <SessionInboxWorkspace sessions={sessions} />
    </div>
  );
}
