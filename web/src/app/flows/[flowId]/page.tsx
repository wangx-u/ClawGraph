import { notFound } from "next/navigation";
import { guidedFlows } from "@/lib/navigation";
import { FlowSteps } from "@/components/dashboard/flow-steps";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";

const flowLinks: Record<string, { primary: string; secondary: string }> = {
  "connect-runtime": { primary: "/access", secondary: "/sessions" },
  "investigate-failure": { primary: "/sessions", secondary: "/supervision" },
  "build-dataset": { primary: "/curation/candidates", secondary: "/datasets" },
  "validate-slice": { primary: "/coverage", secondary: "/evaluation" },
  "review-feedback": { primary: "/feedback", secondary: "/curation/cohorts/cohort_train_001" }
};

export default async function FlowPage({
  params
}: {
  params: Promise<{ flowId: string }>;
}) {
  const { flowId } = await params;
  const flow = guidedFlows.find((item) => item.id === flowId);

  if (!flow) {
    notFound();
  }

  const links = flowLinks[flow.id];

  return (
    <div className="space-y-6">
      <PageHeader
        title={flow.title}
        description={flow.description}
        primaryAction={<Button href={links.primary} variant="primary">打开主工作区</Button>}
        secondaryAction={<Button href={links.secondary} variant="secondary">打开辅助工作区</Button>}
      />

      <div className="grid gap-6 xl:grid-cols-[1fr_0.95fr]">
        <FlowSteps flow={flow} />
        <Card eyebrow="执行清单" title="这个流程要达成什么" strong>
          <div className="space-y-3">
            {flow.steps.map((step) => (
              <div className="panel-soft rounded-2xl p-4" key={step.title}>
                <div className="font-medium">{step.title}</div>
                <div className="mt-2 text-sm text-[color:var(--text-muted)]">{step.detail}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
