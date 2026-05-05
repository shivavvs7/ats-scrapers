"""Lever scraper.

Lever exposes a public JSON board at:
    https://api.lever.co/v0/postings/{slug}?mode=json

Includes location, team, commitment, and (rarely) salary range hints.
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

API_TEMPLATE = "https://api.lever.co/v0/postings/{slug}?mode=json"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.5

_LEVER_INTERVAL_MAP = {
    "1-YEAR": "YEAR",
    "PER-YEAR-SALARY": "YEAR",
    "1-MONTH": "MONTH",
    "1-WEEK": "WEEK",
    "1-DAY": "DAY",
    "1-HOUR": "HOUR",
    "PER-HOUR-WAGE": "HOUR",
    "YEAR": "YEAR",
    "MONTH": "MONTH",
    "WEEK": "WEEK",
    "DAY": "DAY",
    "HOUR": "HOUR",
}


@ScraperRegistry.register(ATSType.LEVER)
class LeverScraper(BaseScraper):
    ats = ATSType.LEVER

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[Job]:
        url = API_TEMPLATE.format(slug=self.company_slug)
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            payload = await self._fetch_with_retry(client, url)
        return [self._parse_job(item) for item in payload]

    async def _fetch_with_retry(
        self, client: httpx.AsyncClient, url: str
    ) -> list[dict[str, Any]]:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Lever fetch failed for {self.company_slug}: {exc}"
                    ) from exc
                await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                continue
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                raise CompanyNotFoundError(
                    f"Lever board not found: {self.company_slug}"
                )
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Lever ({self.company_slug}) returned "
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
                f"Lever returned {response.status_code} for {self.company_slug}"
            )
        raise ScraperError(f"Lever ({self.company_slug}) exhausted retries")

    def _parse_job(self, item: dict[str, Any]) -> Job:
        categories = item.get("categories") or {}
        commitment = categories.get("commitment")
        salary_range = item.get("salaryRange") or {}
        salary_min = salary_range.get("min")
        salary_max = salary_range.get("max")
        salary_currency = salary_range.get("currency")
        salary_interval = (salary_range.get("interval") or "").upper()
        salary_period = _LEVER_INTERVAL_MAP.get(salary_interval)

        raw: dict[str, Any] = {}
        if categories:
            raw["categories"] = categories
        for k in ("workplaceType", "country", "tags", "additionalPlain"):
            v = item.get(k)
            if v:
                raw[k] = v

        is_remote = None
        wp = (item.get("workplaceType") or "").lower()
        if wp in {"remote", "hybrid"}:
            is_remote = wp == "remote"

        return Job(
            url=item["hostedUrl"],
            title=item["text"],
            company=self.company_slug,
            ats_type=ATSType.LEVER,
            ats_id=item["id"],
            location=categories.get("location"),
            department=categories.get("department"),
            team=categories.get("team"),
            commitment=commitment,
            apply_url=item.get("applyUrl"),
            is_remote=is_remote,
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=salary_currency,
            salary_period=salary_period,
            posted_at=_parse_ms(item.get("createdAt")),
            fetched_at=datetime.now(),
            raw=raw or None,
        )


def _parse_ms(value: int | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value / 1000)
    except (ValueError, OSError):
        return None
