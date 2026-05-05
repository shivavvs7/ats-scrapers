import { useEffect, useState } from "react";

function read(): string | null {
  if (typeof window === "undefined") return null;
  const raw = window.location.hash.replace(/^#\/?/, "");
  return raw.length > 0 ? decodeURIComponent(raw) : null;
}

export function useHashRoute(): [string | null, (next: string | null) => void] {
  const [value, setValue] = useState<string | null>(read);

  useEffect(() => {
    const onChange = () => setValue(read());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const set = (next: string | null) => {
    if (next == null) {
      history.pushState(null, "", window.location.pathname + window.location.search);
      setValue(null);
    } else {
      window.location.hash = `/${encodeURIComponent(next)}`;
    }
  };

  return [value, set];
}
