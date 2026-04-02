import { Badge } from "@/components/ui/badge";
import { TopBarSearch } from "@/components/layout/top-bar-search";
import type { DataSourceMeta, SearchItem } from "@/lib/types";

type TopBarProps = {
  meta: DataSourceMeta;
  items: SearchItem[];
};

export function TopBar({ meta, items }: TopBarProps) {

  return (
    <div className="surface mb-6 flex flex-col gap-4 rounded-[1.35rem] p-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex flex-wrap items-center gap-3">
        <div className="rounded-full border border-slate-200 bg-white/75 px-3 py-2 text-xs text-[color:var(--text-muted)]">
          工作区：clawgraph
        </div>
        <div className="rounded-full border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-700">
          环境：{meta.configuredMode}
        </div>
        <div className="rounded-full border border-slate-200 bg-white/75 px-3 py-2 text-xs text-[color:var(--text-muted)]">
          语言：中文
        </div>
        <div className="rounded-full border border-slate-200 bg-white/75 px-3 py-2 text-xs text-[color:var(--text-muted)]">
          时间：最近 7 天
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <TopBarSearch items={items} />
        <Badge tone={meta.status === "prod" ? "success" : meta.status === "prod-fallback" ? "warning" : "info"}>
          {meta.statusText}
        </Badge>
      </div>
    </div>
  );
}
