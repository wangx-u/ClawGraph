import type { ReactNode } from "react";

type DataTableProps = {
  headers: string[];
  rows: ReactNode[][];
};

export function DataTable({ headers, rows }: DataTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full border-separate border-spacing-y-2 text-left text-sm">
        <thead>
          <tr>
            {headers.map((header) => (
              <th className="px-3 py-2 text-xs font-medium uppercase tracking-[0.16em] text-[color:var(--text-soft)]" key={header}>
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr className="transition hover:-translate-y-[1px]" key={index}>
              {row.map((cell, cellIndex) => (
                <td
                  className="border-y border-[color:var(--line)] bg-white/80 px-3 py-3 text-[color:var(--text-muted)] first:rounded-l-2xl first:border-l last:rounded-r-2xl last:border-r"
                  key={cellIndex}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
