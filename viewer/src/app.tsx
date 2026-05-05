import { useEffect, useState } from "react";
import { DatasetList } from "./components/dataset-list";
import { DatasetView } from "./components/dataset-view";
import { Header } from "./components/header";
import { HeaderPreview } from "./components/header-preview";
import {
  fetchManifest,
  findDataset,
  manifestToDatasets,
  type Dataset,
  type Manifest,
} from "./lib/manifest";
import { useHashRoute } from "./lib/hash";

type State =
  | { status: "loading" }
  | { status: "ready"; manifest: Manifest; datasets: Dataset[] }
  | { status: "error"; message: string };

export function App() {
  const [route, setRoute] = useHashRoute();
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    const ctrl = new AbortController();
    fetchManifest(ctrl.signal)
      .then((manifest) =>
        setState({
          status: "ready",
          manifest,
          datasets: manifestToDatasets(manifest),
        }),
      )
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        const message =
          err instanceof Error ? err.message : "Failed to load manifest.";
        setState({ status: "error", message });
      });
    return () => ctrl.abort();
  }, []);

  const dataset =
    state.status === "ready" ? findDataset(state.datasets, route) : undefined;

  const isHeaderPreview = route === "_headers";
  const lastUpdated =
    state.status === "ready" ? new Date(state.manifest.generated_at) : null;

  return (
    <div className="flex min-h-full flex-col">
      <Header onHome={() => setRoute(null)} lastUpdated={lastUpdated} />
      <main className="flex-1">
        {isHeaderPreview ? (
          <HeaderPreview onBack={() => setRoute(null)} />
        ) : state.status === "error" ? (
          <ErrorScreen message={state.message} />
        ) : dataset ? (
          <DatasetView dataset={dataset} onBack={() => setRoute(null)} />
        ) : (
          <DatasetList
            manifest={state.status === "ready" ? state.manifest : null}
            datasets={state.status === "ready" ? state.datasets : null}
            onSelect={(d) => setRoute(d.id)}
          />
        )}
      </main>
    </div>
  );
}

function ErrorScreen({ message }: { message: string }) {
  return (
    <div className="mx-auto max-w-2xl px-6 py-20">
      <h1 className="font-mono text-xl">Could not load datasets.</h1>
      <p className="mt-3 text-[var(--muted)]">{message}</p>
      <p className="mt-6 font-mono text-xs text-[var(--muted)]">
        Manifest URL: storage.stapply.ai/jobhive/v1/manifest.json
      </p>
    </div>
  );
}
