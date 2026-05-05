import { useMemo, useState } from "react";
import { formatNumber } from "../lib/csv";

type Props = {
  columns: string[];
  rows: string[][];
};

const PAGE_SIZE = 50;

export function DataTable({ columns, rows }: Props) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) => r.some((cell) => cell.toLowerCase().includes(q)));
  }, [rows, query]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const start = safePage * PAGE_SIZE;
  const visible = filtered.slice(start, start + PAGE_SIZE);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-sm">
          <input
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
            placeholder="Search rows…"
            className="w-full rounded-md border border-[var(--line)] bg-transparent px-3 py-2 font-mono text-sm placeholder:text-[var(--muted)] focus:border-[var(--fg)] focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-3 font-mono text-xs text-[var(--muted)]">
          <span>
            {formatNumber(filtered.length)} / {formatNumber(rows.length)} rows
          </span>
          <div className="flex items-center overflow-hidden rounded-md border border-[var(--line)]">
            <button
              type="button"
              disabled={safePage === 0}
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              className="px-3 py-1.5 transition-colors hover:bg-[color-mix(in_oklab,var(--fg)_6%,transparent)] disabled:opacity-30 disabled:hover:bg-transparent"
            >
              ←
            </button>
            <span className="border-x border-[var(--line)] px-3 py-1.5">
              {safePage + 1} / {totalPages}
            </span>
            <button
              type="button"
              disabled={safePage >= totalPages - 1}
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              className="px-3 py-1.5 transition-colors hover:bg-[color-mix(in_oklab,var(--fg)_6%,transparent)] disabled:opacity-30 disabled:hover:bg-transparent"
            >
              →
            </button>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto rounded-md border border-[var(--line)]">
        <table className="w-full border-collapse font-mono text-xs">
          <thead className="sticky top-0 bg-[var(--bg)]">
            <tr className="border-b border-[var(--line)]">
              {columns.map((c, i) => (
                <th
                  key={`${c}-${i}`}
                  className="whitespace-nowrap px-3 py-2 text-left font-medium text-[var(--muted)]"
                >
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.map((row, i) => (
              <tr
                key={start + i}
                className="border-b border-[var(--line)] last:border-0 hover:bg-[color-mix(in_oklab,var(--fg)_3%,transparent)]"
              >
                {columns.map((_, j) => (
                  <td
                    key={j}
                    className="max-w-xs truncate px-3 py-2 align-top"
                    title={row[j] ?? ""}
                  >
                    {renderCell(row[j] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
            {visible.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-3 py-12 text-center text-[var(--muted)]"
                >
                  No rows match.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function renderCell(value: string) {
  if (/^https?:\/\//.test(value)) {
    return (
      <a
        href={value}
        target="_blank"
        rel="noreferrer"
        className="underline decoration-[var(--line)] underline-offset-2 hover:decoration-[var(--fg)]"
      >
        {value}
      </a>
    );
  }
  return value;
}
