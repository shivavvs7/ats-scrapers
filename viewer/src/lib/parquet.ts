import type { FileMetaData } from "hyparquet";

export type ParquetData = {
  columns: string[];
  rows: string[][];
  totalRows: number;
  rowsLoaded: number;
  bytes: number;
};

export const PARQUET_INITIAL_ROW_LIMIT = 10_000;

export type ProgressFn = (phase: "metadata" | "rows", info?: string) => void;

export async function fetchParquet(
  url: string,
  byteLength: number | undefined,
  rowLimit: number = PARQUET_INITIAL_ROW_LIMIT,
  signal?: AbortSignal,
  onProgress?: ProgressFn,
): Promise<ParquetData> {
  // Code-split: hyparquet + compressors load only when a parquet is requested.
  const [
    { asyncBufferFromUrl, parquetMetadataAsync, parquetReadObjects },
    { compressors },
  ] = await Promise.all([import("hyparquet"), import("hyparquet-compressors")]);

  onProgress?.("metadata");
  const file = await asyncBufferFromUrl({
    url,
    byteLength,
    requestInit: signal ? { signal } : undefined,
  });
  const metadata = await parquetMetadataAsync(file);
  const totalRows = Number(metadata.num_rows);
  const rowEnd = Math.max(0, Math.min(totalRows, rowLimit));

  onProgress?.("rows");
  const rawRows =
    rowEnd > 0
      ? await parquetReadObjects({
          file,
          metadata,
          rowStart: 0,
          rowEnd,
          compressors,
        })
      : [];

  const columns = inferColumns(metadata, rawRows);
  const rows = rawRows.map((r) => columns.map((c) => stringifyCell(r[c])));

  return {
    columns,
    rows,
    totalRows,
    rowsLoaded: rows.length,
    bytes: byteLength ?? 0,
  };
}

function inferColumns(
  metadata: FileMetaData,
  rows: Record<string, unknown>[],
): string[] {
  if (rows.length > 0) return Object.keys(rows[0]!);
  const schema = metadata.schema ?? [];
  return schema
    .slice(1)
    .map((s) => s.name)
    .filter((n): n is string => typeof n === "string");
}

function stringifyCell(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "bigint") return v.toString();
  if (typeof v === "number") return Number.isFinite(v) ? String(v) : "";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (v instanceof Date) return v.toISOString();
  if (v instanceof Uint8Array) {
    try {
      return new TextDecoder("utf-8", { fatal: false }).decode(v);
    } catch {
      return `<bytes:${v.byteLength}>`;
    }
  }
  if (Array.isArray(v) || typeof v === "object") {
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}
