"use client";

type FilterGroup = {
  id: string;
  label: string;
  value: string;
  options: Array<{
    id: string;
    label: string;
  }>;
  onChange: (value: string) => void;
};

type FilterBarProps = {
  groups: FilterGroup[];
};

export function FilterBar({ groups }: FilterBarProps) {
  if (!groups.length) {
    return null;
  }

  return (
    <div className="surface rounded-[1.25rem] p-4">
      <div className="space-y-4">
        {groups.map((group) => (
          <div className="space-y-2" key={group.id}>
            <div className="text-[11px] uppercase tracking-[0.18em] text-[color:var(--text-soft)]">
              {group.label}
            </div>
            <div className="flex flex-wrap gap-2">
              {group.options.map((option) => (
                <button
                  className={
                    group.value === option.id
                      ? "rounded-full border border-sky-200 bg-sky-50 px-3 py-1.5 text-xs text-sky-700 transition"
                      : "rounded-full border border-slate-200 bg-white/80 px-3 py-1.5 text-xs text-[color:var(--text-muted)] transition hover:border-sky-100 hover:bg-sky-50/70"
                  }
                  key={option.id}
                  onClick={() => group.onChange(option.id)}
                  type="button"
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
