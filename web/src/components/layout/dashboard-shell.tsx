import type { ReactNode } from "react";
import { getDashboardBundle } from "@/lib/data-source";
import { buildPipelineStageSummaries } from "@/lib/pipeline";
import { buildSearchIndex } from "@/lib/search";
import { JobTray } from "@/components/layout/job-tray";
import { PipelineNavigator } from "@/components/layout/pipeline-navigator";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { TopBar } from "@/components/layout/top-bar";

type DashboardShellProps = {
  children: ReactNode;
};

export async function DashboardShell({ children }: DashboardShellProps) {
  const { bundle, meta } = await getDashboardBundle();
  const searchItems = buildSearchIndex(bundle);
  const pipelineStages = buildPipelineStageSummaries(bundle);

  return (
    <div className="mx-auto max-w-[1820px] space-y-6 px-4 py-4 lg:px-6">
      <TopBar items={searchItems} meta={meta} />
      <PipelineNavigator stages={pipelineStages} />
      <div className="flex gap-6">
        <SidebarNav stages={pipelineStages} />
        <main className="min-w-0 flex-1 space-y-6">{children}<JobTray jobs={bundle.jobs} /></main>
      </div>
    </div>
  );
}
