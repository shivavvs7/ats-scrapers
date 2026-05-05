"""Amazon careers scraper.

Amazon has two job APIs:

1. `GET https://www.amazon.jobs/en/search.json?result_limit=N&offset=N`
   Public, paginated, but **capped at 10,000 results** (the underlying search
   index just stops returning past that offset). This is what the legacy
   scraper used and where we used to lose ~half the postings.

2. `POST https://www.amazon.jobs/api/jobs/search`
   Internal but unauthenticated. Returns `found` = the real total (≈20K),
   richer field shapes, and supports `filters[]` for bucketing past the 10K
   pagination cap.

We use the POST endpoint and bucket by country when the result set exceeds
the cap. Per-country pagination is well under 10K for every Amazon market.
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

API_URL = "https://www.amazon.jobs/api/jobs/search"
PAGE_SIZE = 100
PAGINATION_CAP = 10_000  # Amazon stops returning hits past this offset.
MAX_CONCURRENCY = 6


@ScraperRegistry.register(ATSType.AMAZON)
class AmazonScraper(BaseScraper):
    """Amazon scraper — `company_slug` is informational; jobs are global."""

    ats = ATSType.AMAZON

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[Job]:
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            first = await self._post(client, start=0, size=1, filters=[])
            total = int(first.get("found") or 0)
            if total == 0:
                return []

            seen: set[str] = set()
            all_jobs: list[Job] = []

            async def consume(start: int, size: int, filters: list[dict[str, Any]]) -> None:
                payload = await self._post(client, start=start, size=size, filters=filters)
                for hit in payload.get("searchHits") or []:
                    job = self._parse_hit(hit)
                    if job.ats_id in seen:
                        continue
                    seen.add(job.ats_id)
                    all_jobs.append(job)

            if total <= PAGINATION_CAP:
                offsets = list(range(0, total, PAGE_SIZE))
                sem = asyncio.Semaphore(MAX_CONCURRENCY)

                async def task(offset: int) -> None:
                    async with sem:
                        await consume(offset, PAGE_SIZE, [])

                await asyncio.gather(*(task(o) for o in offsets))
                return all_jobs

            # Total exceeds cap — bucket by country facet so each bucket fits.
            countries = _extract_facet_values(first.get("facets") or [], "country")
            sem = asyncio.Semaphore(MAX_CONCURRENCY)

            async def country_bucket(code: str, count: int) -> None:
                # Each country is well under PAGINATION_CAP at Amazon's scale.
                local_total = min(count, PAGINATION_CAP)
                offsets = list(range(0, local_total, PAGE_SIZE))

                async def page_task(offset: int) -> None:
                    async with sem:
                        await consume(
                            offset,
                            PAGE_SIZE,
                            [{"field": "country", "values": [code]}],
                        )

                await asyncio.gather(*(page_task(o) for o in offsets))

            await asyncio.gather(*(country_bucket(c, n) for c, n in countries))
            return all_jobs

    async def _post(
        self,
        client: httpx.AsyncClient,
        *,
        start: int,
        size: int,
        filters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            response = await client.post(
                API_URL,
                json={
                    "searchType": "JOB_SEARCH",
                    "start": start,
                    "size": size,
                    "filters": filters,
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0",
                    "Accept-Encoding": "identity",  # avoid zstd issues
                },
            )
        except httpx.HTTPError as exc:
            raise ScraperError(f"Amazon fetch failed at offset={start}: {exc}") from exc
        if response.status_code == 400:
            # Past the pagination cap — return empty so caller stops.
            return {"searchHits": [], "found": 0}
        if response.status_code != 200:
            raise ScraperError(
                f"Amazon returned {response.status_code} at offset={start}: "
                f"{response.text[:120]}"
            )
        return response.json()

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
