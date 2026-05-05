# URLs needing `httpcloak` or `Browserbase` instead of `httpx`

Reference for which sites refuse plain `httpx` and what alternative client gets
through. When adding a new ATS scraper or discovery target, check this list
first to decide which client to use.

**Defaults**: `httpx` first → `httpcloak` if Cloudflare → `Browserbase` if
Akamai/anti-bot.

## Per-URL test matrix

Tested via 3 clients on every row.

| URL | `httpx` | `httpcloak` | Browserbase | Cause | Used by |
|---|:---:|:---:|:---:|---|---|
| `https://www.jazzhr.com/` | ❌ 403 | ✅ 200 | ✅ 200 (347KB) | Cloudflare | JazzHR discovery |
| `https://www.jazzhr.com/customers` | ❌ 403 | ✅ 200 | ✅ 200 (295KB) | Cloudflare | JazzHR discovery |
| `https://app.jazz.co` | ❌ 403 | ✅ 200 | ✅ 200 (78KB) | Cloudflare + redirect to login | JazzHR — auth wall after |
| `https://applytojob.com` | ❌ 403 | ✅ 200 | ✅ 200 (347KB, → jazzhr) | Cloudflare + 301 | JazzHR root |
| `https://{slug}.applytojob.com/apply/jobs` | ❌ 403 | ✅ 200 | ✅ 200 | Cloudflare | JazzHR per-tenant validation |
| `https://info.jazzhr.com/` | ❌ timeout | ❓ 302 | ✅ 200 (347KB → jazzhr) | DNS/Origin flaky | — |
| `https://www.tesla.com/cua-api/apps/careers/state` | ❌ 403 | ❓ TBD | ⚠️ **429 (rate-limited)** | Akamai bot detection. With Browserbase **proxies=true** it goes through but throttles. Need backoff. | Tesla scraper (currently raises NotImplementedError) |
| `https://www.metacareers.com/jobs` | ⚠️ 200 (CSR, no data) | ❌ same | ✅ 200 (442KB rendered) | CSR site — needs real browser to execute JS | Meta scraper |

Legend: ✅ works, ❌ blocked/empty, ⚠️ partially works, ❓ not yet tested.

## Notes per row

- **Tesla** — Browserbase with `proxies: true` flips the response from 403
  to 429. That's a meaningful step: Akamai now lets the request through but
  rate-limits the residential IP pool. With exponential backoff + sticky
  session, the API is exploitable. Without proxies (vanilla Browserbase
  headless), Tesla still 403s.
- **Meta** — both `httpx` and `httpcloak` return 200 with empty / CSR HTML.
  Browserbase actually renders the page so the data is in the response body.
  This is the right tool for any CSR-heavy careers site.
- **JazzHR family** — `httpcloak` is enough (and 10× cheaper than Browserbase).
  Use Browserbase only if `httpcloak` ever stops working.

## Where `httpx` works fine (don't waste time)

All ATS APIs we already use:
- `boards-api.greenhouse.io`, `api.lever.co`, `api.ashbyhq.com`,
  `apply.workable.com/api/v1`, `api.smartrecruiters.com/v1`,
  `api.rippling.com/platform/api/ats/v1`,
  `{slug}.recruitee.com/api/offers`,
  `{slug}.bamboohr.com/careers` (catch-all but no auth wall),
  `{slug}.teamtailor.com/`,
  `{slug}.jobs.personio.com/search.json`,
  `{co}.wd{N}.myworkdayjobs.com/wday/cxs/...`

Big-tech custom APIs we ship:
- `www.amazon.jobs/en/search.json`,
  `apply.careers.microsoft.com/api/pcsx/search`,
  `nvidia.eightfold.ai/api/pcsx/search`,
  `api.lifeattiktok.com/.../job/posts`,
  `www.uber.com/api/loadSearchJobsResults`,
  `jobs.apple.com/api/v1/search` (after CSRF dance)

## Cheat-sheets

### httpcloak (sync, fast, $0)

```python
import httpcloak

r = httpcloak.get(
    "https://www.jazzhr.com/customers",
    timeout=15,
    headers={"Accept": "text/html"},
)
# Available presets: chrome-143-{macos|windows|linux}, chrome-131-*
```

### Browserbase Fetch (real browser, ~1-3s/req, ~$0.005/req)

```python
import os, httpx

r = httpx.post(
    "https://api.browserbase.com/v1/fetch",
    headers={
        "X-BB-API-Key": os.environ["BROWSERBASE_API_KEY"],
        "Content-Type": "application/json",
    },
    json={
        "url": "https://www.metacareers.com/jobs",
        "allowRedirects": True,   # follow 30x
        "proxies": True,           # residential IPs (helps with Akamai)
    },
    timeout=90,
)
data = r.json()
upstream_status = data["statusCode"]   # the actual server status
content = data["content"]              # the rendered HTML / JSON
headers = data["headers"]              # response headers
```

### Decision tree

```
GET site →
  ├─ 200 ok                                    → httpx
  ├─ 403 + "cf-ray" header                     → httpcloak (Cloudflare)
  ├─ 403 + "akamai" / no useful header         → Browserbase (proxies=true) + retry on 429
  ├─ 200 but content is JS shell / empty       → Browserbase (renders JS)
  └─ everything else                           → httpx with proper UA + headers
```

## In `company_discovery.py`

`PLATFORMS` config supports `"client": "httpcloak"` per platform; default is
`httpx`. Browserbase isn't wired into the discovery pipeline yet — wire it
when needed for a site that beats httpcloak (e.g., if Tesla discovery becomes
worth doing).

## Update policy

When you find a new URL that needs a non-httpx client:
1. Run the 3-client probe (httpx, httpcloak, Browserbase) — there's a
   reproducible script in this repo's history; ask me to recreate.
2. Append a row in the matrix above with the verdict.
3. If Browserbase with proxies fails, the only path forward is interactive
   browser session (Playwright with stealth) — not currently in the toolbox.
