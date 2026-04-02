import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  description: string;
  primaryAction?: ReactNode;
  secondaryAction?: ReactNode;
};

export function PageHeader({
  title,
  description,
  primaryAction,
  secondaryAction
}: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
      <div className="max-w-3xl">
        <div className="mb-2 text-[11px] uppercase tracking-[0.2em] text-[color:var(--text-soft)]">
          ClawGraph 控制台
        </div>
        <h1 className="text-3xl font-semibold md:text-4xl">{title}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[color:var(--text-muted)]">{description}</p>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {secondaryAction}
        {primaryAction}
      </div>
    </div>
  );
}
