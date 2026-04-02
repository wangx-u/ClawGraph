import type { ReactNode } from "react";
import { getDashboardBundle } from "@/lib/data-source";
import { buildSearchIndex } from "@/lib/search";
import { JobTray } from "@/components/layout/job-tray";
import { RightRail } from "@/components/layout/right-rail";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { TopBar } from "@/components/layout/top-bar";

type DashboardShellProps = {
  children: ReactNode;
};

export async function DashboardShell({ children }: DashboardShellProps) {
  const { bundle, meta } = await getDashboardBundle();
  const searchItems = buildSearchIndex(bundle);

  return (
    <div className="mx-auto max-w-[1820px] px-4 py-4 lg:px-6">
      <TopBar items={searchItems} meta={meta} />
      <div className="flex gap-6">
        <SidebarNav />
        <main className="min-w-0 flex-1 space-y-6">{children}<JobTray jobs={bundle.jobs} /></main>
        <RightRail />
      </div>
    </div>
  );
}
