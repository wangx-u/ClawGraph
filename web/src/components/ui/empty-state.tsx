import { Button } from "@/components/ui/button";

type EmptyStateProps = {
  title: string;
  description: string;
  actionLabel: string;
  actionHref: string;
};

export function EmptyState({ title, description, actionLabel, actionHref }: EmptyStateProps) {
  return (
    <div className="surface flex min-h-64 flex-col items-center justify-center rounded-[1.35rem] p-8 text-center">
      <div className="mb-3 text-[11px] uppercase tracking-[0.2em] text-[color:var(--text-soft)]">Empty state</div>
      <h2 className="text-2xl font-semibold">{title}</h2>
      <p className="mt-3 max-w-xl text-sm text-[color:var(--text-muted)]">{description}</p>
      <Button className="mt-6" href={actionHref} variant="primary">
        {actionLabel}
      </Button>
    </div>
  );
}
