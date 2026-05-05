type Props = {
  onHome: () => void;
  lastUpdated?: Date | null;
};

const LOGO_MARK = "https://storage.stapply.ai/assets/stapply_small.svg";
const MANIFEST_URL = "https://storage.stapply.ai/jobhive/v1/manifest.json";

const EXTERNAL_TABS: { label: string; href: string }[] = [
  { label: "manifest", href: MANIFEST_URL },
  { label: "github", href: "https://github.com/stapply-ai" },
];

export function Header({ onHome, lastUpdated }: Props) {
  return (
    <header className="border-b border-[var(--line)]">
      <div className="mx-auto max-w-7xl px-6 pt-4">
        <div className="flex items-center justify-between gap-6">
          <button
            type="button"
            onClick={onHome}
            className="inline-flex items-center gap-3 focus:outline-none"
          >
            <img src={LOGO_MARK} alt="" className="h-5 w-5" />
            <span className="font-mono text-sm font-medium tracking-tight">
              stapply
            </span>
            <span className="text-[var(--muted)]">/</span>
            <span className="rounded-sm bg-[color-mix(in_oklab,var(--fg)_8%,transparent)] px-1.5 py-0.5 font-mono text-xs">
              data
            </span>
          </button>
          <span className="hidden font-mono text-[10px] uppercase tracking-widest text-[var(--muted)] sm:inline">
            v1 · public dataset
          </span>
        </div>

        <nav className="-mb-px mt-3 flex items-end gap-1">
          <Tab onClick={onHome} active label="datasets" />
          {EXTERNAL_TABS.map((t) => (
            <Tab key={t.label} href={t.href} external label={t.label} />
          ))}
          <span className="mb-2 ml-auto font-mono text-[10px] text-[var(--muted)]">
            {lastUpdated ? `updated ${relativeTime(lastUpdated)}` : ""}
          </span>
        </nav>
      </div>
    </header>
  );
}

function Tab({
  label,
  active,
  onClick,
  href,
  external,
}: {
  label: string;
  active?: boolean;
  onClick?: () => void;
  href?: string;
  external?: boolean;
}) {
  const className = `relative px-3 py-2 font-mono text-xs transition-colors ${
    active
      ? "text-[var(--fg)]"
      : "text-[var(--muted)] hover:text-[var(--fg)]"
  }`;
  const indicator = active ? (
    <span
      aria-hidden
      className="absolute inset-x-3 bottom-0 h-px"
      style={{ background: "var(--c-violet)" }}
    />
  ) : null;

  if (href) {
    return (
      <a
        href={href}
        target={external ? "_blank" : undefined}
        rel={external ? "noreferrer" : undefined}
        className={className}
      >
        {label}
        {external && (
          <span aria-hidden className="ml-1 opacity-60">
            ↗
          </span>
        )}
        {indicator}
      </a>
    );
  }
  return (
    <button type="button" onClick={onClick} className={className}>
      {label}
      {indicator}
    </button>
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
