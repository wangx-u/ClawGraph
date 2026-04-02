import { getDashboardBundle } from "@/lib/data-source";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page-header";

export default async function AccessPage() {
  const { meta } = await getDashboardBundle();

  return (
    <div className="space-y-6">
      <PageHeader
        title="接入"
        description="用低侵入的 proxy-first 方式接入 ClawGraph，再逐步补强上下文与语义，提升 replay 与导出保真度。"
        primaryAction={<Button href="/flows/connect-runtime" variant="primary">创建接入流程</Button>}
        secondaryAction={<Button href="/sessions" variant="secondary">验证最新流量</Button>}
      />

      <Card eyebrow="连接状态" title="环境健康度" strong>
        <DataTable
          headers={["环境", "代理健康度", "每分钟请求", "错误率", "平均延迟", "最近事件"]}
          rows={[
            ["prod", "健康", "430", "0.4%", "320ms", "2 秒前"],
            ["shadow", "告警", "58", "3.1%", "510ms", "12 秒前"]
          ]}
        />
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
        <Card eyebrow="接入模式" title="推荐接入梯度">
          <div className="grid gap-3">
            {[
              ["透明代理", "只改 endpoint，就能立刻采集真实流量。"],
              ["代理 + 上下文 Header", "补 durable id，提升 session、run 与 parent 关联精度。"],
              ["代理 + 语义契约", "在关键 retry、fallback、route 决策点补语义事件。"]
            ].map(([title, body]) => (
              <div className="panel-soft rounded-[1.15rem] p-4" key={title}>
                <div className="font-medium">{title}</div>
                <p className="mt-2 text-sm text-[color:var(--text-muted)]">{body}</p>
              </div>
            ))}
          </div>
        </Card>

        <Card eyebrow="检查清单" title="身份与语义覆盖率">
          <div className="grid gap-3 md:grid-cols-2">
            {[
              "session_id 覆盖率 93%",
              "run_id 覆盖率 88%",
              "user_id 覆盖率 76%",
              "thread_id 覆盖率 69%",
              "retry_declared 覆盖率 41%",
              "fallback_declared 覆盖率 34%",
              "controller_route_decided 覆盖率 22%",
              `数据源模式：${meta.statusText}`
            ].map((item) => (
              <div className="panel-soft rounded-2xl p-4 text-sm text-[color:var(--text-muted)]" key={item}>
                {item}
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
