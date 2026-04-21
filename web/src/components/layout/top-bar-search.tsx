"use client";

import { startTransition, useDeferredValue, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { SearchItem } from "@/lib/types";

type TopBarSearchProps = {
  items: SearchItem[];
};

export function TopBarSearch({ items }: TopBarSearchProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const deferredQuery = useDeferredValue(query);
  const normalizedQuery = deferredQuery.trim().toLowerCase();
  const results = items
    .filter((item) => {
      if (!normalizedQuery) {
        return true;
      }

      const haystack = [item.title, item.subtitle, item.kind, ...(item.keywords ?? [])]
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalizedQuery);
    })
    .slice(0, normalizedQuery ? 8 : 6);

  useEffect(() => {
    setActiveIndex(0);
  }, [normalizedQuery]);

  const navigateTo = (href: string) => {
    setOpen(false);
    setQuery("");
    startTransition(() => {
      router.push(href);
    });
  };

  return (
    <div className="relative min-w-[320px] flex-1 lg:max-w-[520px]">
      <div className="rounded-[1.2rem] border border-slate-200 bg-white/90 px-4 py-3 shadow-sm">
        <input
          className="w-full bg-transparent text-sm text-[color:var(--text)] outline-none placeholder:text-[color:var(--text-soft)]"
          onBlur={() => {
            window.setTimeout(() => setOpen(false), 120);
          }}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={(event) => {
            if (!results.length) {
              if (event.key === "Escape") {
                setOpen(false);
              }
              return;
            }

            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActiveIndex((current) => (current + 1) % results.length);
            }

            if (event.key === "ArrowUp") {
              event.preventDefault();
              setActiveIndex((current) => (current - 1 + results.length) % results.length);
            }

            if (event.key === "Enter") {
              event.preventDefault();
              navigateTo(results[activeIndex]?.href ?? results[0].href);
            }

            if (event.key === "Escape") {
              setOpen(false);
            }
          }}
          placeholder="搜索会话 / 运行 / 切片 / 数据快照 / 评分卡"
          value={query}
        />
      </div>

      {open ? (
        <div className="surface-strong absolute left-0 right-0 top-[calc(100%+0.6rem)] z-30 rounded-[1.2rem] p-3">
          <div className="mb-2 flex items-center justify-between px-2 text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">
            <span>命令搜索</span>
            <span>{results.length} 条</span>
          </div>
          <div className="space-y-1">
            {results.length ? (
              results.map((item, index) => (
                <button
                  className={
                    index === activeIndex
                      ? "tech-highlight flex w-full items-start justify-between gap-3 rounded-[1rem] px-3 py-3 text-left"
                      : "flex w-full items-start justify-between gap-3 rounded-[1rem] px-3 py-3 text-left transition hover:bg-sky-50/80"
                  }
                  key={item.id}
                  onMouseEnter={() => setActiveIndex(index)}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    navigateTo(item.href);
                  }}
                  type="button"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full border border-slate-200 bg-white/80 px-2 py-0.5 text-[10px] tracking-[0.16em] text-[color:var(--text-soft)]">
                        {item.kind}
                      </span>
                      <span className="truncate text-sm font-medium">{item.title}</span>
                    </div>
                    <div className="mt-1 truncate text-xs text-[color:var(--text-muted)]">{item.subtitle}</div>
                  </div>
                  <span className="text-[11px] text-[color:var(--text-soft)]">Enter</span>
                </button>
              ))
            ) : (
              <div className="rounded-[1rem] px-3 py-6 text-center text-sm text-[color:var(--text-muted)]">
                没有匹配项，换一个 session、slice 或 scorecard 关键词试试。
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
