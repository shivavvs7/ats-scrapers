"""Amazon careers scraper.

Amazon has two job APIs:

1. ``GET https://www.amazon.jobs/en/search.json?result_limit=N&offset=N``
   Public, snake-case payload (``id_icims`` / ``job_path`` /
   ``normalized_location``). **Honors filter query params** like
   ``business_category[]=aws``. Capped at 10,000 results per query —
   bucketing required to exceed it.

2. ``POST https://www.amazon.jobs/api/jobs/search``
   Internal but unauthenticated. Returns ``found`` = the real total (≈20K)
   and exposes facets, but **its ``filters`` body is silently ignored** —
   every filtered POST returns the unfiltered count. We use it only to
   discover the true total and the business-category facet values; all
   actual job fetching runs through the GET endpoint.

Strategy:

  - POST once with ``size=1`` to read ``found`` (true total ≈ 20K) and the
    ``businessCategory`` facet (≈61 values, largest ``aws`` = ~6K).
  - If ``total <= 10K`` → GET-paginate the unfiltered endpoint.
  - Else → for each business category, GET-paginate that bucket. Every
    Amazon business category sits well under 10K so a single layer
    suffices.

Earlier rev bucketed by ``country`` via the POST endpoint; that path
silently capped at 10K because the POST endpoint ignores the filter and
every bucket request returned the same first 10K results.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from jobhive.exceptions import ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

if TYPE_CHECKING:
    from typing import Any

FACET_URL = "https://www.amazon.jobs/api/jobs/search"  # POST — facet discovery only
SEARCH_URL = "https://www.amazon.jobs/en/search.json"   # GET — actual job fetching
PAGE_SIZE = 100
PAGINATION_CAP = 10_000  # Amazon stops returning hits past offset+limit = 10K.
MAX_CONCURRENCY = 6
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.5


@ScraperRegistry.register(ATSType.AMAZON)
class AmazonScraper(BaseScraper):
    """Amazon scraper — `company_slug` is informational; jobs are global."""

    ats = ATSType.AMAZON

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[Job]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            facets_payload = await self._post_facets(client)
            total = int(facets_payload.get("found") or 0)
            if total == 0:
                return []

            seen: set[str] = set()
            all_jobs: list[Job] = []
            sem = asyncio.Semaphore(MAX_CONCURRENCY)

            def absorb(jobs_payload: list[dict[str, Any]]) -> None:
                for hit in jobs_payload:
                    job = self._parse_hit(hit)
                    if not job.ats_id or job.ats_id in seen:
                        continue
                    seen.add(job.ats_id)
                    all_jobs.append(job)

            async def get_page(extra_params: dict[str, str], offset: int) -> None:
                async with sem:
                    payload = await self._get(
                        client,
                        params={**extra_params, "result_limit": PAGE_SIZE, "offset": offset},
                    )
                absorb(payload.get("jobs") or [])

            if total <= PAGINATION_CAP:
                offsets = list(range(0, total, PAGE_SIZE))
                await asyncio.gather(*(get_page({}, o) for o in offsets))
                return all_jobs

            # Past the cap — bucket by businessCategory. The POST facet uses
            # the same lowercase-dashed slugs that the GET endpoint accepts
            # in ``business_category[]`` (verified empirically: ``aws`` →
            # ~6.1K hits, ``operations`` → ~800).
            categories = _extract_facet_values(
                facets_payload.get("facets") or [], "businessCategory"
            )
            if not categories:
                # Facet missing — fall back to capped pagination so we at
                # least get the first 10K rather than crashing.
                offsets = list(range(0, PAGINATION_CAP, PAGE_SIZE))
                await asyncio.gather(*(get_page({}, o) for o in offsets))
                return all_jobs

            async def category_bucket(name: str, count: int) -> None:
                local_total = min(count, PAGINATION_CAP)
                offsets = list(range(0, local_total, PAGE_SIZE))
                await asyncio.gather(*(
                    get_page({"business_category[]": name}, o) for o in offsets
                ))

            await asyncio.gather(*(category_bucket(n, c) for n, c in categories))
            return all_jobs

    async def _post_facets(self, client: httpx.AsyncClient) -> dict[str, Any]:
        """Single POST call to read the true total and the businessCategory
        facet. The POST endpoint's ``filters`` body is broken (returns
        unfiltered counts), so we never use it for actual fetching."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.post(
                    FACET_URL,
                    json={"searchType": "JOB_SEARCH", "start": 0, "size": 1, "filters": []},
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "User-Agent": "Mozilla/5.0",
                        "Accept-Encoding": "identity",
                    },
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES:
                    raise ScraperError(f"Amazon facet POST failed: {exc}") from exc
                await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                continue
            if response.status_code == 200:
                return response.json()
            if response.status_code in {429} or 500 <= response.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Amazon facet POST {response.status_code} after {MAX_RETRIES} retries"
                    )
                await asyncio.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                continue
            raise ScraperError(
                f"Amazon facet POST {response.status_code}: {response.text[:120]}"
            )
        raise ScraperError("Amazon facet POST exhausted retries")

    async def _get(
        self,
        client: httpx.AsyncClient,
        *,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(
                    SEARCH_URL,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "Mozilla/5.0",
                        "Accept-Encoding": "identity",
                    },
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Amazon GET failed at {params}: {exc}"
                    ) from exc
                await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                continue
            if response.status_code == 200:
                return response.json()
            if response.status_code == 400:
                # Past the cap — return empty so the caller stops.
                return {"jobs": [], "hits": 0}
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Amazon GET {response.status_code} after {MAX_RETRIES} "
                        f"retries at {params}"
                    )
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after) if retry_after and retry_after.isdigit()
                    else RETRY_BASE_DELAY * (2 ** attempt)
                )
                await asyncio.sleep(delay)
                continue
            raise ScraperError(
                f"Amazon GET {response.status_code} at {params}: "
                f"{response.text[:120]}"
            )
        raise ScraperError(f"Amazon GET exhausted retries at {params}")

    def _parse_hit(self, hit: dict[str, Any]) -> Job:
        # Each searchHit wraps `fields` whose values are arrays.
        fields = hit.get("fields") if isinstance(hit, dict) else None
        item: dict[str, Any] = {}
        if isinstance(fields, dict):
            item = {k: (v[0] if isinstance(v, list) and v else v) for k, v in fields.items()}
        else:
            item = hit if isinstance(hit, dict) else {}

        # Amazon's API uses camelCase keys ``icimsJobId`` / ``urlNextStep``
        # / ``normalizedLocation`` / ``createdDate``. The legacy snake_case
        # aliases (``id_icims`` / ``job_path`` / ``normalized_location`` /
        # ``posted_date``) are kept as fallbacks so an API rename in either
        # direction won't silently nuke ``ats_id`` (which is the dedup key
        # — empty ats_ids collapse the entire result set to a single row).
        ats_id = str(
            item.get("icimsJobId") or item.get("id_icims")
            or item.get("jobCode") or item.get("id") or hit.get("id", "")
        )
        path = (
            item.get("urlNextStep") or item.get("job_path")
            or item.get("jobUrl") or ""
        )
        if path and not path.startswith("http"):
            url = f"https://www.amazon.jobs{path}"
        elif path:
            url = path
        else:
            url = f"https://www.amazon.jobs/en/jobs/{ats_id}"

        raw: dict[str, Any] = {}
        for k in ("teamCategory", "businessCategory", "jobFamily",
                  "schedule", "scheduleType", "businessJobDescription",
                  "city", "state", "country"):
            v = item.get(k)
            if v:
                raw[k] = v

        return Job(
            url=url,
            title=item.get("title") or item.get("jobTitle") or "Untitled",
            company="Amazon",
            ats_type=ATSType.AMAZON,
            ats_id=ats_id,
            location=(
                item.get("normalizedLocation")
                or item.get("normalized_location")
                or item.get("location")
            ),
            team=item.get("teamCategory") if isinstance(item.get("teamCategory"), str) else None,
            commitment=item.get("scheduleType") if isinstance(item.get("scheduleType"), str) else None,
            requisition_id=ats_id if ats_id else None,
            posted_at=_parse_iso(
                item.get("updatedDate")
                or item.get("createdDate")
                or item.get("posted_date")
                or item.get("postedDate")
            ),
            fetched_at=datetime.now(),
            raw=raw or None,
        )


def _extract_facet_values(facets: list[dict[str, Any]], field: str) -> list[tuple[str, int]]:
    for facet in facets:
        if isinstance(facet, dict) and facet.get("name") == field:
            return [
                (v.get("name", ""), int(v.get("count") or 0))
                for v in facet.get("values") or []
                if isinstance(v, dict) and v.get("name") and (v.get("count") or 0) > 0
            ]
    return []


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
