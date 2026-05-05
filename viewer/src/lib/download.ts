export async function downloadFile(
  url: string,
  filename: string,
  onProgress?: (loaded: number, total: number | null) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const totalHeader = res.headers.get("content-length");
  const total = totalHeader ? parseInt(totalHeader, 10) : null;

  let blob: Blob;
  if (res.body && onProgress) {
    const reader = res.body.getReader();
    const chunks: Uint8Array[] = [];
    let loaded = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) {
        chunks.push(value);
        loaded += value.byteLength;
        onProgress(loaded, total);
      }
    }
    blob = new Blob(chunks as BlobPart[], {
      type: res.headers.get("content-type") ?? "application/octet-stream",
    });
  } else {
    blob = await res.blob();
  }

  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoke after a tick so the browser has time to start the download.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

export function filenameFromUrl(url: string): string {
  const path = new URL(url).pathname;
  const last = path.split("/").pop() ?? "download";
  return last || "download";
}
