import { useEffect, useState, type ReactNode } from "react";
import { fetchCsv, formatBytes, formatNumber } from "../lib/csv";
import { downloadFile, filenameFromUrl } from "../lib/download";
import {
  fetchParquet,
  PARQUET_INITIAL_ROW_LIMIT,
  type ParquetData,
} from "../lib/parquet";
import type { Dataset } from "../lib/manifest";
import { DataTable } from "./data-table";

type Props = {
  dataset: Dataset;
  onBack: () => void;
};

type Source = "csv" | "parquet";

type LoadedData = {
  source: Source;
  columns: string[];
  rows: string[][];
  totalRows: number;
  rowsLoaded: number;
};

type State =
  | { status: "idle" }
  | { status: "loading"; phase: string }
  | { status: "ready"; data: LoadedData }
  | { status: "error"; message: string };

const CSV_AUTO_LOAD_LIMIT = 25 * 1024 * 1024; // 25 MB compressed-on-wire CSV
const PARQUET_AUTO_LOAD_LIMIT = 60 * 1024 * 1024; // 60 MB parquet on disk

function pickAutoSource(dataset: Dataset): Source | null {
  const csvOk =
    dataset.csv != null &&
    (dataset.csvSize ?? Number.POSITIVE_INFINITY) <= CSV_AUTO_LOAD_LIMIT;
  if (csvOk) return "csv";
  const parquetOk =
    dataset.parquet != null &&
    (dataset.parquetSize ?? Number.POSITIVE_INFINITY) <= PARQUET_AUTO_LOAD_LIMIT;
  if (parquetOk) return "parquet";
  return null;
}

export function DatasetView({ dataset, onBack }: Props) {
  const initialSource = pickAutoSource(dataset);
  const [source, setSource] = useState<Source | null>(initialSource);
  const [state, setState] = useState<State>(
    initialSource ? { status: "loading", phase: "fetching" } : { status: "idle" },
  );

  useEffect(() => {
    if (!source) {
      setState({ status: "idle" });
      return;
    }
    const ctrl = new AbortController();
    let cancelled = false;
    setState({ status: "loading", phase: source === "parquet" ? "metadata" : "fetching" });

    const run = async () => {
      try {
        if (source === "csv" && dataset.csv) {
          const data = await fetchCsv(dataset.csv, ctrl.signal);
          if (cancelled) return;
          setState({
            status: "ready",
            data: {
              source: "csv",
              columns: data.columns,
              rows: data.rows,
              totalRows: data.rows.length,
              rowsLoaded: data.rows.length,
            },
          });
        } else if (source === "parquet" && dataset.parquet) {
          const data: ParquetData = await fetchParquet(
            dataset.parquet,
            dataset.parquetSize,
            PARQUET_INITIAL_ROW_LIMIT,
            ctrl.signal,
            (phase) =>
              !cancelled &&
              setState({
                status: "loading",
                phase: phase === "metadata" ? "reading metadata" : "reading rows",
              }),
          );
          if (cancelled) return;
          setState({
            status: "ready",
            data: {
              source: "parquet",
              columns: data.columns,
              rows: data.rows,
              totalRows: data.totalRows,
              rowsLoaded: data.rowsLoaded,
            },
          });
        }
      } catch (err: unknown) {
        if (cancelled || ctrl.signal.aborted) return;
        const message = err instanceof Error ? err.message : "Failed to load.";
        setState({ status: "error", message });
      }
    };
    run();

    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [source, dataset.csv, dataset.parquet, dataset.parquetSize]);

  const switchTo = (next: Source) => setSource(next);
  const loadAll = async () => {
    if (!dataset.parquet) return;
    setState({ status: "loading", phase: "loading all rows" });
    try {
      const data = await fetchParquet(
        dataset.parquet,
        dataset.parquetSize,
        Number.MAX_SAFE_INTEGER,
      );
      setState({
        status: "ready",
        data: {
          source: "parquet",
          columns: data.columns,
          rows: data.rows,
          totalRows: data.totalRows,
          rowsLoaded: data.rowsLoaded,
        },
      });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load.";
      setState({ status: "error", message });
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-10">
      <button
        type="button"
        onClick={onBack}
        className="mb-6 inline-flex items-center gap-1.5 font-mono text-xs text-[var(--muted)] transition-colors hover:text-[var(--fg)]"
      >
        <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M11 3l-5 5 5 5" strokeLinecap="square" />
        </svg>
        all datasets
      </button>

      <header className="mb-8 flex flex-col gap-4 border-b border-[var(--line)] pb-6 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="mb-2 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-widest text-[var(--muted)]">
            <span
              aria-hidden
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{ background: datasetAccent(dataset.category) }}
            />
            {dataset.category.replace(/-/g, " · ")}
          </p>
          <h1 className="font-mono text-2xl tracking-tight">{dataset.name}</h1>
          <p className="mt-2 max-w-2xl text-[var(--muted)]">
            {dataset.description}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {dataset.csv && (
            <DownloadButton
              variant="primary"
              label="csv"
              url={dataset.csv}
              size={dataset.csvSize}
            />
          )}
          {dataset.parquet && (
            <DownloadButton
              variant="ghost"
              label="parquet"
              url={dataset.parquet}
              size={dataset.parquetSize}
            />
          )}
        </div>
      </header>

      <Stats dataset={dataset} state={state} />

      {(dataset.csv || dataset.parquet) && (
        <FormatToggle
          dataset={dataset}
          source={source}
          onChange={switchTo}
        />
      )}

      <div className="mt-6">
        {state.status === "idle" && (
          <IdleNotice dataset={dataset} onLoad={(s) => switchTo(s)} />
        )}
        {state.status === "loading" && <Skeleton phase={state.phase} />}
        {state.status === "error" && <Errored message={state.message} />}
        {state.status === "ready" && (
          <>
            {state.data.source === "parquet" &&
              state.data.rowsLoaded < state.data.totalRows && (
                <PartialBanner
                  rowsLoaded={state.data.rowsLoaded}
                  totalRows={state.data.totalRows}
                  onLoadAll={loadAll}
                />
              )}
            <DataTable columns={state.data.columns} rows={state.data.rows} />
          </>
        )}
      </div>
    </div>
  );
}

function FormatToggle({
  dataset,
  source,
  onChange,
}: {
  dataset: Dataset;
  source: Source | null;
  onChange: (s: Source) => void;
}) {
  const options: { id: Source; label: string; available: boolean }[] = [
    { id: "csv", label: "csv", available: dataset.csv != null },
    { id: "parquet", label: "parquet", available: dataset.parquet != null },
  ];
  const visible = options.filter((o) => o.available);
  if (visible.length < 2) return null;
  return (
    <div className="mt-4 flex items-center gap-2 font-mono text-xs">
      <span className="text-[var(--muted)]">view:</span>
      <div className="inline-flex overflow-hidden rounded-md border border-[var(--line)]">
        {visible.map((o) => (
          <button
            key={o.id}
            type="button"
            onClick={() => onChange(o.id)}
            className={`px-3 py-1.5 transition-colors ${
              source === o.id
                ? "bg-[var(--fg)] text-[var(--bg)]"
                : "hover:bg-[color-mix(in_oklab,var(--fg)_6%,transparent)]"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Stats({ dataset, state }: { dataset: Dataset; state: State }) {
  const stats = [
    {
      label: "rows",
      value: formatNumber(dataset.rows),
      color: "var(--c-blue)",
    },
    {
      label: "columns",
      value:
        state.status === "ready"
          ? formatNumber(state.data.columns.length)
          : "—",
      color: "var(--c-amber)",
    },
    {
      label: "csv size",
      value: dataset.csvSize != null ? formatBytes(dataset.csvSize) : "—",
      color: "var(--c-emerald)",
    },
    {
      label: "parquet size",
      value:
        dataset.parquetSize != null ? formatBytes(dataset.parquetSize) : "—",
      color: "var(--c-violet)",
    },
  ];
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-[var(--line)] bg-[var(--line)] md:grid-cols-4">
      {stats.map((s) => (
        <div key={s.label} className="relative bg-[var(--bg)] px-4 py-3">
          <span
            aria-hidden
            className="absolute inset-x-0 top-0 h-px"
            style={{ background: s.color }}
          />
          <dt className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-[var(--muted)]">
            <span
              aria-hidden
              className="inline-block h-1 w-1 rounded-full"
              style={{ background: s.color }}
            />
            {s.label}
          </dt>
          <dd className="mt-1 font-mono text-lg">{s.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function IdleNotice({
  dataset,
  onLoad,
}: {
  dataset: Dataset;
  onLoad: (s: Source) => void;
}) {
  if (!dataset.csv && !dataset.parquet) {
    return (
      <div className="rounded-md border border-[var(--line)] p-6 text-sm">
        <p className="font-mono text-[var(--fg)]">No preview available.</p>
      </div>
    );
  }
  return (
    <div className="rounded-md border border-[var(--line)] p-6 text-sm">
      <p className="font-mono text-[var(--fg)]">Large file.</p>
      <p className="mt-2 text-[var(--muted)]">
        Both formats are larger than the auto-load threshold. Pick one to stream
        in, or download for offline analysis with DuckDB / Polars / pandas.
      </p>
      <div className="mt-4 flex gap-2">
        {dataset.csv && (
          <button
            type="button"
            onClick={() => onLoad("csv")}
            className="inline-flex items-center rounded-md border border-[var(--line)] px-3 py-2 font-mono text-xs transition-colors hover:border-[var(--fg)]"
          >
            load csv ({formatBytes(dataset.csvSize ?? 0)})
          </button>
        )}
        {dataset.parquet && (
          <button
            type="button"
            onClick={() => onLoad("parquet")}
            className="inline-flex items-center rounded-md border border-[var(--line)] px-3 py-2 font-mono text-xs transition-colors hover:border-[var(--fg)]"
          >
            load parquet ({formatBytes(dataset.parquetSize ?? 0)})
          </button>
        )}
      </div>
    </div>
  );
}

function PartialBanner({
  rowsLoaded,
  totalRows,
  onLoadAll,
}: {
  rowsLoaded: number;
  totalRows: number;
  onLoadAll: () => void;
}) {
  return (
    <p className="mb-3 font-mono text-xs text-[var(--muted)]">
      Showing first{" "}
      <span className="text-[var(--fg)]">{formatNumber(rowsLoaded)}</span> of{" "}
      <span className="text-[var(--fg)]">{formatNumber(totalRows)}</span> rows.{" "}
      <button
        type="button"
        onClick={onLoadAll}
        className="underline decoration-[var(--line)] underline-offset-2 transition-colors hover:text-[var(--fg)] hover:decoration-[var(--fg)]"
      >
        load all
      </button>
    </p>
  );
}

function datasetAccent(category: Dataset["category"]): string {
  switch (category) {
    case "all-jobs":
      return "var(--c-amber)";
    case "by-ats":
      return "var(--c-blue)";
    case "companies":
    case "companies-by-ats":
      return "var(--c-emerald)";
    case "by-date":
      return "var(--c-violet)";
  }
}

function Skeleton({ phase }: { phase: string }) {
  return (
    <div className="space-y-2">
      <div className="inline-flex items-center gap-2 font-mono text-xs text-[var(--muted)]">
        <span
          aria-hidden
          className="inline-block h-1.5 w-1.5 animate-pulse rounded-full"
          style={{ background: "var(--c-violet)" }}
        />
        {phase}…
      </div>
      <div className="h-9 w-full animate-pulse rounded-md bg-[var(--line)]" />
      <div className="h-72 w-full animate-pulse rounded-md bg-[var(--line)]" />
    </div>
  );
}

function Errored({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-[var(--line)] p-6 font-mono text-sm">
      <p className="mb-2 text-[var(--fg)]">Could not load dataset.</p>
      <p className="text-[var(--muted)]">{message}</p>
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="h-3.5 w-3.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <path d="M8 2v9M4 7l4 4 4-4M3 14h10" strokeLinecap="square" />
    </svg>
  );
}

type DownloadStatus =
  | { phase: "idle" }
  | { phase: "downloading"; loaded: number; total: number | null }
  | { phase: "error"; message: string };

function DownloadButton({
  variant,
  label,
  url,
  size,
}: {
  variant: "primary" | "ghost";
  label: string;
  url: string;
  size: number | undefined;
}) {
  const [status, setStatus] = useState<DownloadStatus>({ phase: "idle" });
  const downloading = status.phase === "downloading";

  const onClick = async () => {
    if (downloading) return;
    setStatus({ phase: "downloading", loaded: 0, total: size ?? null });
    try {
      await downloadFile(url, filenameFromUrl(url), (loaded, total) => {
        setStatus({ phase: "downloading", loaded, total: total ?? size ?? null });
      });
      setStatus({ phase: "idle" });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Download failed.";
      setStatus({ phase: "error", message });
    }
  };

  const base =
    "inline-flex items-center gap-2 rounded-md px-3 py-2 font-mono text-xs transition-colors disabled:opacity-60";
  const cls =
    variant === "primary"
      ? `${base} bg-[var(--fg)] text-[var(--bg)] hover:opacity-90`
      : `${base} border border-[var(--line)] hover:border-[var(--fg)]`;

  const sizeMuted =
    variant === "primary" ? "opacity-60" : "text-[var(--muted)]";

  let trailing: ReactNode = null;
  if (downloading) {
    const pct =
      status.total && status.total > 0
        ? Math.min(100, Math.round((status.loaded / status.total) * 100))
        : null;
    trailing = (
      <span className={sizeMuted}>
        · {pct != null ? `${pct}%` : formatBytes(status.loaded)}
      </span>
    );
  } else if (status.phase === "error") {
    trailing = <span className={sizeMuted}>· retry</span>;
  } else if (size != null) {
    trailing = <span className={sizeMuted}>· {formatBytes(size)}</span>;
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={downloading}
      title={status.phase === "error" ? status.message : undefined}
      className={cls}
    >
      {downloading ? <Spinner /> : <DownloadIcon />}
      {label}
      {trailing}
    </button>
  );
}

function Spinner() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="h-3.5 w-3.5 animate-spin"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <circle cx="8" cy="8" r="6" opacity="0.25" />
      <path d="M14 8a6 6 0 0 0-6-6" strokeLinecap="round" />
    </svg>
  );
}
