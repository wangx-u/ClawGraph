"use client";

import { useState } from "react";

type FilterBarProps = {
  filters: string[];
};

export function FilterBar({ filters }: FilterBarProps) {
  const [active, setActive] = useState<string | null>(filters[0] ?? null);

  return (
    <div className="surface rounded-[1.25rem] p-3">
      <div className="flex flex-wrap gap-2">
        {filters.map((filter) => (
          <button
            className={
              active === filter
                ? "rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs text-sky-700 transition"
                : "rounded-full border border-slate-200 bg-white/80 px-3 py-1.5 text-xs text-[color:var(--text-muted)] transition hover:border-sky-100 hover:bg-sky-50/70"
            }
            key={filter}
            onClick={() => setActive(filter)}
          >
            {filter}
          </button>
        ))}
      </div>
    </div>
  );
}
