"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";

type TabItem = {
  id: string;
  label: string;
  content: ReactNode;
};

type TabsProps = {
  items: TabItem[];
  active?: string;
};

export function Tabs({ items, active }: TabsProps) {
  const [current, setCurrent] = useState(active ?? items[0]?.id);
  const activeItem = useMemo(
    () => items.find((item) => item.id === current) ?? items[0],
    [current, items]
  );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2">
        {items.map((item) => {
          const isActive = item.id === current;
          return (
            <button
              className={cn(
                "rounded-full border px-3 py-1.5 text-xs tracking-[0.08em] transition",
                isActive
                  ? "border-sky-200 bg-[linear-gradient(135deg,rgba(50,119,255,0.12),rgba(22,204,179,0.08))] text-sky-700 shadow-sm"
                  : "border-slate-200 bg-white/85 text-[color:var(--text-muted)] hover:bg-sky-50"
              )}
              key={item.id}
              onClick={() => setCurrent(item.id)}
              type="button"
            >
              {item.label}
            </button>
          );
        })}
      </div>
      <div>{activeItem?.content}</div>
    </div>
  );
}
