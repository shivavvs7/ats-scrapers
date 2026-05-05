/**
 * Header proposals — five distinct directions inspired by:
 *   1. Linear (linear.app)        — command-bar / floating frosted nav
 *   2. Vercel (vercel.com)        — sharp brand + product tabs with active underline
 *   3. Observable (observablehq)  — data-tool metadata strip + masthead
 *   4. Editorial newspaper        — display logotype, dated rule lines
 *   5. Terminal / IDE             — prompt-driven, monospace, kbd hints
 *
 * Reachable at #/_headers — pick a number and I'll wire it as the live header.
 */

const ASSETS = "https://storage.stapply.ai/assets";
const LOGO_DARK = `${ASSETS}/stapply_white.svg`;
const LOGO_LIGHT = `${ASSETS}/stapply_black.svg`;
const LOGO_MARK = `${ASSETS}/stapply_small.svg`;

const NAV: { label: string; href: string }[] = [
  { label: "stapply.ai", href: "https://stapply.ai" },
  { label: "map", href: "https://map.stapply.ai" },
  { label: "github", href: "https://github.com/stapply-ai" },
];

type Props = {
  onBack: () => void;
};

export function HeaderPreview({ onBack }: Props) {
  return (
    <div className="mx-auto max-w-5xl px-6 py-12 md:py-16">
      <button
        type="button"
        onClick={onBack}
        className="mb-8 inline-flex items-center gap-1.5 font-mono text-xs text-[var(--muted)] transition-colors hover:text-[var(--fg)]"
      >
        ← back
      </button>

      <h1 className="text-2xl font-medium tracking-tight md:text-3xl">
        Header proposals
      </h1>
      <p className="mt-2 max-w-xl text-[var(--muted)]">
        Five distinct directions, each leaning into a real product reference.
        Reply with a number and I&apos;ll wire it as the live header.
      </p>

      <div className="mt-12 space-y-14">
        <Variant
          n={1}
          title="Command bar"
          inspiration="linear.app"
          subtitle="Floating frosted bar with a fake ⌘K, live indicator, pill nav."
        >
          <V1Linear />
        </Variant>

        <Variant
          n={2}
          title="Product tabs"
          inspiration="vercel.com"
          subtitle="Strict brand mark, mono nav as tabs with an accent active underline."
        >
          <V2Vercel />
        </Variant>

        <Variant
          n={3}
          title="Metadata strip"
          inspiration="observablehq.com"
          subtitle="Top status bar with live KPIs, then a clean masthead row underneath."
        >
          <V3Observable />
        </Variant>

        <Variant
          n={4}
          title="Editorial masthead"
          inspiration="newspaper / The Browser Co."
          subtitle="Display logotype between rule lines, dateline + edition number on the right."
        >
          <V4Editorial />
        </Variant>

        <Variant
          n={5}
          title="Terminal"
          inspiration="iTerm / read.cv / Posthog console"
          subtitle="Prompt-style brand with blinking cursor, kbd hints, machine-readable subline."
        >
          <V5Terminal />
        </Variant>
      </div>
    </div>
  );
}

function Variant({
  n,
  title,
  inspiration,
  subtitle,
  children,
}: {
  n: number;
  title: string;
  inspiration: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="inline-flex items-baseline gap-2 font-mono text-xs uppercase tracking-widest text-[var(--muted)]">
          <span className="text-[var(--fg)]">option {n}</span> · {title}
          <span className="text-[10px] normal-case tracking-normal opacity-70">
            (inspired by {inspiration})
          </span>
        </h2>
      </div>
      <p className="mb-3 max-w-2xl text-xs text-[var(--muted)]">{subtitle}</p>
      <div className="overflow-hidden rounded-lg border border-[var(--line)] bg-[var(--bg)]">
        {children}
      </div>
    </section>
  );
}

/* ============================================================== */
/*  1.  COMMAND BAR — Linear-style                                */
/* ============================================================== */

function V1Linear() {
  return (
    <div className="bg-[color-mix(in_oklab,var(--bg)_80%,transparent)] backdrop-blur">
      <div className="grid grid-cols-[auto_1fr_auto] items-center gap-6 px-5 py-3">
        {/* brand */}
        <div className="inline-flex items-center gap-2.5">
          <img src={LOGO_MARK} alt="" className="h-5 w-5" />
          <span className="font-mono text-sm font-medium">stapply</span>
          <span className="font-mono text-sm text-[var(--muted)]">/ data</span>
        </div>

        {/* fake command palette */}
        <button
          type="button"
          className="mx-auto flex w-full max-w-md items-center justify-between gap-3 rounded-md border border-[var(--line)] bg-[color-mix(in_oklab,var(--fg)_3%,transparent)] px-3 py-1.5 font-mono text-xs text-[var(--muted)] transition-colors hover:border-[var(--fg)]"
        >
          <span className="inline-flex items-center gap-2">
            <SearchIcon />
            search 1,044,206 jobs across 15 ATS…
          </span>
          <kbd className="inline-flex items-center gap-1 rounded border border-[var(--line)] bg-[var(--bg)] px-1.5 font-mono text-[10px]">
            ⌘ K
          </kbd>
        </button>

        {/* status + nav */}
        <div className="flex items-center gap-4 font-mono text-xs">
          <span className="inline-flex items-center gap-1.5 text-[var(--muted)]">
            <span
              aria-hidden
              className="relative inline-flex h-1.5 w-1.5"
            >
              <span
                className="absolute inset-0 animate-ping rounded-full opacity-75"
                style={{ background: "var(--c-emerald)" }}
              />
              <span
                className="relative inline-block h-1.5 w-1.5 rounded-full"
                style={{ background: "var(--c-emerald)" }}
              />
            </span>
            live
          </span>
          {NAV.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="rounded-md px-2 py-1 text-[var(--muted)] hover:bg-[color-mix(in_oklab,var(--fg)_5%,transparent)] hover:text-[var(--fg)]"
            >
              {l.label}
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ============================================================== */
/*  2.  PRODUCT TABS — Vercel-style                               */
/* ============================================================== */

function V2Vercel() {
  const tabs = [
    { label: "datasets", active: true, href: "#" },
    { label: "manifest", active: false, href: "https://storage.stapply.ai/jobhive/v1/manifest.json" },
    { label: "stapply.ai", active: false, href: "https://stapply.ai" },
    { label: "github", active: false, href: "https://github.com/stapply-ai" },
  ];
  return (
    <div>
      <div className="flex items-center justify-between gap-6 px-5 pt-4">
        <div className="inline-flex items-center gap-3">
          <img src={LOGO_MARK} alt="" className="h-5 w-5" />
          <span className="font-mono text-sm font-medium tracking-tight">
            stapply
          </span>
          <span className="text-[var(--muted)]">/</span>
          <span className="rounded-sm bg-[color-mix(in_oklab,var(--fg)_8%,transparent)] px-1.5 py-0.5 font-mono text-xs">
            data
          </span>
        </div>
        <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--muted)]">
          v1 · public dataset
        </span>
      </div>
      <nav className="-mb-px mt-3 flex items-end gap-1 px-3">
        {tabs.map((t) => (
          <a
            key={t.label}
            href={t.href}
            className={`relative px-3 py-2 font-mono text-xs transition-colors ${
              t.active
                ? "text-[var(--fg)]"
                : "text-[var(--muted)] hover:text-[var(--fg)]"
            }`}
          >
            {t.label}
            {t.active && (
              <span
                aria-hidden
                className="absolute inset-x-3 bottom-0 h-px"
                style={{ background: "var(--c-violet)" }}
              />
            )}
          </a>
        ))}
        <span className="mb-2 ml-auto font-mono text-[10px] text-[var(--muted)]">
          updated 14h ago
        </span>
      </nav>
      <div className="h-px bg-[var(--line)]" />
    </div>
  );
}

/* ============================================================== */
/*  3.  METADATA STRIP — Observable-style                         */
/* ============================================================== */

function V3Observable() {
  const stats = [
    { label: "live", value: null, color: "var(--c-emerald)", live: true },
    { label: "v", value: "1.0", color: "var(--c-muted)" },
    { label: "updated", value: "14h ago", color: "var(--c-violet)" },
    { label: "jobs", value: "1,044,206", color: "var(--c-blue)" },
    { label: "companies", value: "13,670", color: "var(--c-emerald)" },
    { label: "ats", value: "15", color: "var(--c-amber)" },
    { label: "license", value: "mit", color: "var(--c-muted)" },
  ];
  return (
    <div>
      {/* top thin metadata strip */}
      <div className="flex items-center gap-x-5 gap-y-1 overflow-x-auto whitespace-nowrap border-b border-[var(--line)] bg-[color-mix(in_oklab,var(--fg)_2%,transparent)] px-5 py-1.5 font-mono text-[10px] uppercase tracking-widest text-[var(--muted)]">
        {stats.map((s, i) => (
          <span key={i} className="inline-flex items-center gap-1.5">
            <span
              aria-hidden
              className={`inline-block h-1 w-1 rounded-full ${
                s.live ? "animate-pulse" : ""
              }`}
              style={{ background: s.color }}
            />
            <span>{s.label}</span>
            {s.value && (
              <span className="text-[var(--fg)]">{s.value}</span>
            )}
          </span>
        ))}
      </div>
      {/* masthead row */}
      <div className="flex items-center justify-between gap-6 px-5 py-4">
        <div className="inline-flex items-baseline gap-3">
          <picture className="block h-6">
            <source srcSet={LOGO_DARK} media="(prefers-color-scheme: dark)" />
            <img src={LOGO_LIGHT} alt="stapply" className="h-6" />
          </picture>
          <span className="font-mono text-sm tracking-tight text-[var(--muted)]">
            / data
          </span>
        </div>
        <nav className="flex items-center gap-5 font-mono text-xs text-[var(--muted)]">
          {NAV.map((l) => (
            <a key={l.label} href={l.href} className="hover:text-[var(--fg)]">
              {l.label}
            </a>
          ))}
        </nav>
      </div>
    </div>
  );
}

/* ============================================================== */
/*  4.  EDITORIAL MASTHEAD — newspaper                            */
/* ============================================================== */

function V4Editorial() {
  return (
    <div className="px-5">
      <div className="flex items-center gap-3 pt-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-[var(--muted)]">
          edition n° 042
        </span>
        <div className="h-px flex-1 bg-[var(--fg)] opacity-30" />
        <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-[var(--muted)]">
          monday · may 04, 2026
        </span>
      </div>
      <div className="flex items-center justify-between gap-6 py-3">
        <div className="inline-flex items-baseline gap-4">
          <picture className="block h-8 md:h-10">
            <source srcSet={LOGO_DARK} media="(prefers-color-scheme: dark)" />
            <img src={LOGO_LIGHT} alt="stapply" className="h-8 md:h-10" />
          </picture>
          <span
            className="font-medium tracking-tight"
            style={{ fontSize: "clamp(1.5rem, 3vw, 2.25rem)" }}
          >
            <span className="text-[var(--muted)]">·</span>{" "}
            <span style={{ color: "var(--c-violet)" }}>data</span>
          </span>
        </div>
        <nav className="hidden items-center gap-4 font-mono text-xs text-[var(--muted)] md:flex">
          {NAV.map((l) => (
            <a key={l.label} href={l.href} className="hover:text-[var(--fg)]">
              {l.label}
            </a>
          ))}
        </nav>
      </div>
      <div className="flex items-center gap-3 pb-3">
        <div className="h-px flex-1 bg-[var(--fg)] opacity-30" />
        <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-[var(--muted)]">
          1,044,206 jobs · 13,670 companies · 15 ats
        </span>
        <div className="h-px flex-1 bg-[var(--fg)] opacity-30" />
      </div>
    </div>
  );
}

/* ============================================================== */
/*  5.  TERMINAL — prompt + kbd hints                             */
/* ============================================================== */

function V5Terminal() {
  return (
    <div className="bg-[color-mix(in_oklab,var(--fg)_3%,transparent)]">
      <div className="grid grid-cols-[auto_1fr_auto] items-center gap-6 px-5 py-3 font-mono text-sm">
        {/* prompt */}
        <div className="inline-flex items-center gap-2">
          <span style={{ color: "var(--c-emerald)" }}>$</span>
          <span className="text-[var(--muted)]">data.stapply.ai</span>
          <span style={{ color: "var(--c-violet)" }}>›</span>
          <span className="cursor-blink inline-block h-4 w-2 align-middle" style={{ background: "var(--fg)" }} />
        </div>

        {/* tech subline */}
        <div className="hidden justify-center text-[10px] uppercase tracking-widest text-[var(--muted)] md:flex">
          <span className="inline-flex items-center gap-3">
            <span style={{ color: "var(--c-blue)" }}>1.04M</span> rows
            <span aria-hidden>·</span>
            <span style={{ color: "var(--c-violet)" }}>zstd</span> parquet
            <span aria-hidden>·</span>
            <span style={{ color: "var(--c-emerald)" }}>public</span>
            <span aria-hidden>·</span>
            <span>mit</span>
          </span>
        </div>

        {/* kbd hints */}
        <div className="flex items-center gap-3 text-[10px] uppercase tracking-widest text-[var(--muted)]">
          {[
            { key: "M", label: "ap", href: "https://map.stapply.ai" },
            { key: "G", label: "h", href: "https://github.com/stapply-ai" },
            { key: "S", label: "tapply", href: "https://stapply.ai" },
          ].map((k) => (
            <a key={k.key} href={k.href} className="inline-flex items-center gap-1 hover:text-[var(--fg)]">
              <kbd className="inline-flex h-5 w-5 items-center justify-center rounded border border-[var(--line)] bg-[var(--bg)] font-mono text-[10px] text-[var(--fg)]">
                {k.key}
              </kbd>
              {k.label}
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}

function SearchIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      className="h-3.5 w-3.5"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
    >
      <circle cx="7" cy="7" r="4.5" />
      <path d="M11 11l3 3" strokeLinecap="square" />
    </svg>
  );
}
