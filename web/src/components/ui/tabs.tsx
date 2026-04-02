"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

type TabsProps = {
  items: string[];
  active?: string;
};

export function Tabs({ items, active }: TabsProps) {
  const [current, setCurrent] = useState(active ?? items[0]);

  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => {
        const isActive = item === current;
        return (
          <button
            className={cn(
              "rounded-full border px-3 py-1.5 text-xs tracking-[0.08em] transition",
              isActive
                ? "border-sky-200 bg-[linear-gradient(135deg,rgba(50,119,255,0.12),rgba(22,204,179,0.08))] text-sky-700 shadow-sm"
                : "border-slate-200 bg-white/85 text-[color:var(--text-muted)] hover:bg-sky-50"
            )}
            key={item}
            onClick={() => setCurrent(item)}
          >
            {item}
          </button>
        );
      })}
    </div>
  );
}
