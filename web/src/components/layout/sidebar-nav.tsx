"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navGroups } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-[280px] shrink-0 xl:block">
      <div className="surface-strong sticky top-4 rounded-[1.6rem] p-4">
        <div className="mb-6">
          <div className="text-[11px] uppercase tracking-[0.22em] text-sky-700/80">ClawGraph</div>
          <div className="mt-2 text-2xl font-semibold">学习数据控制台</div>
          <p className="mt-2 text-sm text-[color:var(--text-muted)]">
            从证据采集、监督、策展到数据快照、评测与受控替代。
          </p>
        </div>
        <div className="space-y-5">
          {navGroups.map((group) => (
            <div key={group.title}>
              <div className="mb-2 px-2 text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">
                {group.title}
              </div>
              <div className="space-y-1">
                {group.items.map((item) => {
                  const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
                  return (
                    <Link
                      className={cn(
                        "block rounded-2xl px-3 py-3 transition",
                        active
                          ? "bg-[linear-gradient(135deg,rgba(50,119,255,0.12),rgba(22,204,179,0.09))] text-[color:var(--text)]"
                          : "text-[color:var(--text-muted)] hover:bg-sky-50 hover:text-[color:var(--text)]"
                      )}
                      href={item.href}
                      key={item.href}
                    >
                      <div className="font-medium">{item.title}</div>
                      <div className="mt-1 text-xs text-inherit/80">{item.description}</div>
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
