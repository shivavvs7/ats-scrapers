import Papa from "papaparse";

export type CsvData = {
  columns: string[];
  rows: string[][];
  bytes: number;
};

export async function fetchCsv(
  url: string,
  signal?: AbortSignal,
): Promise<CsvData> {
  const res = await fetch(url, { signal });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} fetching ${url}`);
  }
  const text = await res.text();
  const bytes = new Blob([text]).size;
  const parsed = Papa.parse<string[]>(text, {
    skipEmptyLines: true,
  });
  if (parsed.errors.length > 0 && parsed.data.length === 0) {
    throw new Error(parsed.errors[0]?.message ?? "CSV parse error");
  }
  const data = parsed.data;
  const columns = (data[0] ?? []).map((c) => String(c));
  const rows = data.slice(1).map((r) => r.map((c) => (c == null ? "" : String(c))));
  return { columns, rows, bytes };
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat("en-US").format(n);
}
