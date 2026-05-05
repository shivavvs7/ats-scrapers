export const MANIFEST_URL =
  "https://storage.stapply.ai/jobhive/v1/manifest.json";

export type ManifestEntry = {
  csv?: string;
  parquet?: string;
  rows: number;
  size_bytes: number;
  parquet_size_bytes?: number;
  sha256: string;
};

export type ManifestStats = {
  ats_count: number;
  total_jobs: number;
  total_companies: number;
  schema_columns: string[];
  schema_version: string;
};

export type Manifest = {
  version: string;
  generated_at: string;
  generator: string;
  stats: ManifestStats;
  all: ManifestEntry;
  by_ats: Record<string, ManifestEntry>;
  by_date: Record<string, ManifestEntry>;
  companies: ManifestEntry;
  companies_by_ats: Record<string, ManifestEntry>;
};

export type Dataset = {
  id: string;
  name: string;
  description: string;
  category: "all-jobs" | "by-ats" | "by-date" | "companies" | "companies-by-ats";
  rows: number;
  csv?: string;
  parquet?: string;
  csvSize?: number;
  parquetSize?: number;
};

export async function fetchManifest(signal?: AbortSignal): Promise<Manifest> {
  const res = await fetch(MANIFEST_URL, { signal, cache: "no-cache" });
  if (!res.ok) throw new Error(`Manifest HTTP ${res.status}`);
  return (await res.json()) as Manifest;
}

export function manifestToDatasets(m: Manifest): Dataset[] {
  const out: Dataset[] = [];

  out.push({
    id: "all-jobs",
    name: "all jobs",
    description: "Every job across every ATS, aggregated.",
    category: "all-jobs",
    rows: m.all.rows,
    csv: undefined,
    parquet: m.all.parquet,
    parquetSize: m.all.parquet_size_bytes,
  });

  out.push({
    id: "all-companies",
    name: "all companies",
    description: "Every company discovered across every ATS.",
    category: "companies",
    rows: m.companies.rows,
    csv: m.companies.csv,
    csvSize: m.companies.size_bytes,
  });

  for (const ats of Object.keys(m.by_ats).sort()) {
    const e = m.by_ats[ats]!;
    out.push({
      id: `jobs-${ats}`,
      name: `jobs · ${ats}`,
      description: `Jobs from the ${ats} ATS.`,
      category: "by-ats",
      rows: e.rows,
      csv: e.csv,
      csvSize: e.size_bytes,
      parquet: e.parquet,
      parquetSize: e.parquet_size_bytes,
    });
  }

  for (const ats of Object.keys(m.companies_by_ats).sort()) {
    const e = m.companies_by_ats[ats]!;
    out.push({
      id: `companies-${ats}`,
      name: `companies · ${ats}`,
      description: `Companies discovered on ${ats}.`,
      category: "companies-by-ats",
      rows: e.rows,
      csv: e.csv,
      csvSize: e.size_bytes,
    });
  }

  return out;
}

export function findDataset(
  datasets: Dataset[],
  id: string | null,
): Dataset | undefined {
  if (!id) return undefined;
  return datasets.find((d) => d.id === id);
}
