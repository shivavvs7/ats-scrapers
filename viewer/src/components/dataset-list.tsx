import { useState, type CSSProperties, type MouseEvent } from "react";
import type { Dataset, Manifest } from "../lib/manifest";
import { formatBytes, formatNumber } from "../lib/csv";
import { downloadFile, filenameFromUrl } from "../lib/download";

type Props = {
  manifest: Manifest | null;
  datasets: Dataset[] | null;
  onSelect: (dataset: Dataset) => void;
};

const CATEGORY_LABELS: Record<Dataset["category"], string> = {
  "all-jobs": "Aggregated",
  companies: "Aggregated",
  "by-ats": "Jobs · per ATS",
  "companies-by-ats": "Companies · per ATS",
  "by-date": "Jobs · by date",
};

const CATEGORY_COLOR: Record<Dataset["category"], string> = {
  "all-jobs": "var(--c-amber)",
  companies: "var(--c-emerald)",
  "by-ats": "var(--c-blue)",
  "companies-by-ats": "var(--c-emerald)",
  "by-date": "var(--c-violet)",
};

const CATEGORY_ORDER: Dataset["category"][] = [
  "all-jobs",
  "by-ats",
  "companies-by-ats",
];

export function DatasetList({ manifest, datasets, onSelect }: Props) {
  const aggregated =
    datasets?.filter(
      (d) => d.category === "all-jobs" || d.category === "companies",
    ) ?? [];
  const grouped = CATEGORY_ORDER.filter((c) => c !== "all-jobs").map(
    (category) => ({
      category,
      items: datasets?.filter((d) => d.category === category) ?? [],
    }),
  );

  const generated = manifest ? new Date(manifest.generated_at) : null;
  const generatedAgo = generated ? relativeTime(generated) : null;

  return (
    <div className="mx-auto max-w-7xl px-6 py-12 md:py-16">
      <section className="mb-14">
        <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-md border border-[var(--line)] bg-[var(--line)] md:grid-cols-4">
          <Stat
            label="jobs"
            value={
              manifest ? formatNumber(manifest.stats.total_jobs) : null
            }
            color="var(--c-blue)"
          />
          <Stat
            label="companies"
            value={
              manifest ? formatNumber(manifest.stats.total_companies) : null
            }
            color="var(--c-emerald)"
          />
          <Stat
            label="ats platforms"
            value={manifest ? String(manifest.stats.ats_count) : null}
            color="var(--c-amber)"
          />
          <Stat
            label="updated"
            value={generatedAgo}
            sub={generated ? generated.toISOString().slice(0, 10) : undefined}
            color="var(--c-violet)"
          />
        </dl>
      </section>

      {datasets ? (
        <>
          <section className="mb-12">
            <SectionHeader
              label="Aggregated"
              colorA="var(--c-amber)"
              colorB="var(--c-emerald)"
              count={aggregated.length}
            />
            <ul className="grid grid-cols-1 gap-px bg-[var(--line)] md:grid-cols-2">
              {aggregated.map((d) => (
                <DatasetCard
                  key={d.id}
                  dataset={d}
                  onSelect={onSelect}
                  accent={CATEGORY_COLOR[d.category]}
                  highlight
                />
              ))}
              <Fillers
                count={aggregated.length}
                cols={[1, 2, 2]}
                color="var(--c-amber)"
                highlight
              />
            </ul>
          </section>

          <div className="space-y-12">
            {grouped.map(({ category, items }) =>
              items.length > 0 ? (
                <section key={category}>
                  <SectionHeader
                    label={CATEGORY_LABELS[category]}
                    colorA={CATEGORY_COLOR[category]}
                    count={items.length}
                  />
                  <ul className="grid grid-cols-1 gap-px bg-[var(--line)] md:grid-cols-2 lg:grid-cols-3">
                    {items.map((d) => (
                      <DatasetCard
                        key={d.id}
                        dataset={d}
                        onSelect={onSelect}
                        accent={CATEGORY_COLOR[category]}
                      />
                    ))}
                    <Fillers
                      count={items.length}
                      cols={[1, 2, 3]}
                      color={CATEGORY_COLOR[category]}
                    />
                  </ul>
                </section>
              ) : null,
            )}
          </div>
        </>
      ) : (
        <ListSkeleton />
      )}
    </div>
  );
}

function ListSkeleton() {
  return (
    <div className="space-y-12">
      {[2, 3, 3].map((cols, i) => (
        <section key={i}>
          <div className="mb-4 h-6 w-40 animate-pulse rounded bg-[var(--line)]" />
          <ul
            className={`grid grid-cols-1 gap-px bg-[var(--line)] md:grid-cols-2 ${
              cols === 3 ? "lg:grid-cols-3" : ""
            }`}
          >
            {Array.from({ length: cols * 2 }).map((_, j) => (
              <li
                key={j}
                className="h-[140px] animate-pulse bg-[var(--bg)]"
                aria-hidden
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function SectionHeader({
  label,
  colorA,
  colorB,
  count,
}: {
  label: string;
  colorA: string;
  colorB?: string;
  count: number;
}) {
  return (
    <div className="mb-4 flex items-center justify-between border-b border-[var(--line)] pb-2">
      <h2 className="inline-flex items-center gap-2 font-mono text-xs uppercase tracking-widest text-[var(--muted)]">
        <span aria-hidden className="inline-flex h-2 w-2 overflow-hidden rounded-[2px]">
          <span className="h-full flex-1" style={{ background: colorA }} />
          {colorB && (
            <span className="h-full flex-1" style={{ background: colorB }} />
          )}
        </span>
        {label}
      </h2>
      <span className="font-mono text-xs text-[var(--muted)]">
        {count} {count === 1 ? "file" : "files"}
      </span>
    </div>
  );
}

function DatasetCard({
  dataset,
  onSelect,
  accent,
  highlight,
}: {
  dataset: Dataset;
  onSelect: (d: Dataset) => void;
  accent: string;
  highlight?: boolean;
}) {
  const size = dataset.csvSize ?? dataset.parquetSize;
  const open = () => onSelect(dataset);
  return (
    <li className="bg-[var(--bg)]">
      <div
        role="button"
        tabIndex={0}
        onClick={open}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            open();
          }
        }}
        style={{ "--card-accent": accent } as CSSProperties}
        className={`group relative flex h-full w-full cursor-pointer flex-col items-start gap-2 p-5 text-left transition-colors hover:bg-[color-mix(in_oklab,var(--card-accent)_5%,transparent)] focus:outline-none focus-visible:bg-[color-mix(in_oklab,var(--card-accent)_8%,transparent)] ${
          highlight ? "min-h-[160px]" : ""
        }`}
      >
        <span
          aria-hidden
          className="absolute inset-x-0 top-0 h-px scale-x-0 origin-left bg-[var(--card-accent)] opacity-0 transition-all duration-300 group-hover:scale-x-100 group-hover:opacity-100 group-focus-visible:scale-x-100 group-focus-visible:opacity-100"
        />
        <div className="flex w-full items-start justify-between gap-3">
          <span className="font-mono text-sm">{dataset.name}</span>
          <QuickDownloads dataset={dataset} />
        </div>
        <span className="text-sm text-[var(--muted)]">{dataset.description}</span>
        <div className="mt-auto flex w-full items-baseline justify-between gap-3 pt-3 font-mono text-xs text-[var(--muted)]">
          <span>{formatNumber(dataset.rows)} rows</span>
          <span className="flex items-center gap-2">
            {size != null && <span>{formatBytes(size)}</span>}
            <span className="hidden text-[var(--muted)] transition-colors group-hover:text-[var(--card-accent)] sm:inline">
              open →
            </span>
          </span>
        </div>
      </div>
    </li>
  );
}

function QuickDownloads({ dataset }: { dataset: Dataset }) {
  if (!dataset.csv && !dataset.parquet) return null;
  return (
    <div className="flex shrink-0 items-center gap-1">
      {dataset.csv && <QuickDownloadButton url={dataset.csv} label="csv" />}
      {dataset.parquet && (
        <QuickDownloadButton url={dataset.parquet} label="parquet" />
      )}
    </div>
  );
}

type QStatus = "idle" | "downloading" | "error";

function QuickDownloadButton({
  url,
  label,
}: {
  url: string;
  label: string;
}) {
  const [status, setStatus] = useState<QStatus>("idle");

  const onClick = async (e: MouseEvent) => {
    e.stopPropagation();
    if (status === "downloading") return;
    setStatus("downloading");
    try {
      await downloadFile(url, filenameFromUrl(url));
      setStatus("idle");
    } catch {
      setStatus("error");
      setTimeout(() => setStatus("idle"), 2000);
    }
  };

  return (
    <button
      type="button"
      onClick={onClick}
      onKeyDown={(e) => e.stopPropagation()}
      title={`download ${label}`}
      className="inline-flex h-6 items-center gap-1 rounded border border-[var(--line)] px-1.5 font-mono text-[10px] uppercase tracking-wider text-[var(--muted)] transition-colors hover:border-[var(--fg)] hover:text-[var(--fg)]"
    >
      {status === "downloading" ? (
        <Spinner3 />
      ) : status === "error" ? (
        "!"
      ) : (
        <DownloadIconSm />
      )}
      <span>{label}</span>
    </button>
  );
}

function DownloadIconSm() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="h-2.5 w-2.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <path d="M8 2v9M4 7l4 4 4-4M3 14h10" strokeLinecap="square" />
    </svg>
  );
}

function Spinner3() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="h-2.5 w-2.5 animate-spin"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <circle cx="8" cy="8" r="6" opacity="0.25" />
      <path d="M14 8a6 6 0 0 0-6-6" strokeLinecap="round" />
    </svg>
  );
}

function Fillers({
  count,
  cols,
  color,
  highlight,
}: {
  count: number;
  cols: [number, number, number]; // [sm, md, lg]
  color: string;
  highlight?: boolean;
}) {
  const [smCols, mdCols, lgCols] = cols;
  const need = (n: number, c: number) => (c - (n % c)) % c;
  const smNeed = need(count, smCols);
  const mdNeed = need(count, mdCols);
  const lgNeed = need(count, lgCols);
  const total = Math.max(smNeed, mdNeed, lgNeed);
  if (total === 0) return null;

  const cells: { key: number; visibility: string }[] = [];
  for (let i = 0; i < total; i++) {
    const vSm = i < smNeed;
    const vMd = i < mdNeed;
    const vLg = i < lgNeed;
    const parts: string[] = [vSm ? "block" : "hidden"];
    if (vMd !== vSm) parts.push(vMd ? "md:block" : "md:hidden");
    if (vLg !== vMd) parts.push(vLg ? "lg:block" : "lg:hidden");
    cells.push({ key: i, visibility: parts.join(" ") });
  }

  return (
    <>
      {cells.map(({ key, visibility }) => (
        <li
          key={`filler-${key}`}
          aria-hidden
          className={`bg-[var(--bg)] ${visibility}`}
        >
          <div
            className={`hatch h-full w-full ${
              highlight ? "min-h-[160px]" : "min-h-[140px]"
            }`}
            style={{ "--hatch-color": color } as CSSProperties}
          />
        </li>
      ))}
    </>
  );
}

function Stat({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string | null;
  sub?: string;
  color: string;
}) {
  return (
    <div className="relative bg-[var(--bg)] px-5 py-4">
      <span
        aria-hidden
        className="absolute inset-x-0 top-0 h-px"
        style={{ background: color }}
      />
      <dt className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest text-[var(--muted)]">
        <span
          aria-hidden
          className="inline-block h-1 w-1 rounded-full"
          style={{ background: color }}
        />
        {label}
      </dt>
      <dd className="mt-1 font-mono text-xl">
        {value ?? <span className="inline-block h-5 w-16 animate-pulse rounded bg-[var(--line)] align-middle" />}
      </dd>
      {sub ? (
        <dd className="font-mono text-xs text-[var(--muted)]">{sub}</dd>
      ) : value === null ? (
        <dd>
          <span className="mt-1 inline-block h-3 w-20 animate-pulse rounded bg-[var(--line)]" />
        </dd>
      ) : null}
    </div>
  );
}

function relativeTime(d: Date): string {
  const diffMs = Date.now() - d.getTime();
  const min = Math.round(diffMs / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const h = Math.round(min / 60);
  if (h < 48) return `${h}h ago`;
  const days = Math.round(h / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.round(days / 30);
  return `${months}mo ago`;
}
