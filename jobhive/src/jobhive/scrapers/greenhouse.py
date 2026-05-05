"""Greenhouse scraper.

Greenhouse exposes a public JSON board at:
    https://boards-api.greenhouse.io/v1/boards/{slug}/jobs

The most permissive ATS API — no auth, no rate limits in practice. Title,
location, and posted_at are reliable; salary is rarely present in the list
endpoint and would require fetching each job page individually.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from jobhive.exceptions import CompanyNotFoundError, ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

if TYPE_CHECKING:
    from typing import Any

API_TEMPLATE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.5


@ScraperRegistry.register(ATSType.GREENHOUSE)
class GreenhouseScraper(BaseScraper):
    ats = ATSType.GREENHOUSE

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[Job]:
        url = API_TEMPLATE.format(slug=self.company_slug)
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            payload = await self._fetch_with_retry(client, url)
        return [self._parse_job(item) for item in payload.get("jobs", [])]

    async def _fetch_with_retry(
        self, client: httpx.AsyncClient, url: str
    ) -> dict[str, Any]:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Greenhouse fetch failed for {self.company_slug}: {exc}"
                    ) from exc
                await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                continue
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                raise CompanyNotFoundError(
                    f"Greenhouse board not found: {self.company_slug}"
                )
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Greenhouse ({self.company_slug}) returned "
                        f"{response.status_code} after {MAX_RETRIES} retries"
                    )
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after) if retry_after and retry_after.isdigit()
                    else RETRY_BASE_DELAY * (2 ** attempt)
                )
                await asyncio.sleep(delay)
                continue
            raise ScraperError(
                f"Greenhouse returned {response.status_code} for {self.company_slug}"
            )
        raise ScraperError(f"Greenhouse ({self.company_slug}) exhausted retries")

    def _parse_job(self, item: dict[str, Any]) -> Job:
        offices = item.get("offices") or []
        departments = item.get("departments") or []
        first_dept = next(
            (d.get("name") for d in departments if isinstance(d, dict) and d.get("name")),
            None,
        )
        metadata = item.get("metadata") or []
        # Greenhouse "metadata" is a list of {name, value, value_type} dicts —
        # custom fields the employer set. Capture verbatim in ``raw``.
        raw: dict[str, Any] = {}
        if metadata:
            raw["metadata"] = metadata
        if departments:
            raw["departments"] = [d.get("name") for d in departments if isinstance(d, dict)]
        if offices:
            raw["offices"] = [o.get("name") for o in offices if isinstance(o, dict)]
        if item.get("internal_job_id") is not None:
            raw["internal_job_id"] = item["internal_job_id"]

        return Job(
            url=item["absolute_url"],
            title=item["title"],
            company=self.company_slug,
            ats_type=ATSType.GREENHOUSE,
            ats_id=str(item["id"]),
            location=(item.get("location") or {}).get("name"),
            department=first_dept,
            requisition_id=str(item["requisition_id"]) if item.get("requisition_id") else None,
            posted_at=_parse_iso(item.get("updated_at")),
            fetched_at=datetime.now(),
            raw=raw or None,
        )


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
