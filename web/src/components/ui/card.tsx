import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type CardProps = {
  title?: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  strong?: boolean;
};

export function Card({ title, eyebrow, action, children, className, strong = false }: CardProps) {
  return (
    <section
      className={cn(
        "rounded-[1.35rem] p-5",
        strong ? "surface-strong" : "surface",
        className
      )}
    >
      {(title || eyebrow || action) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div className="space-y-1">
            {eyebrow ? <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">{eyebrow}</div> : null}
            {title ? <h2 className="text-lg font-semibold">{title}</h2> : null}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}
