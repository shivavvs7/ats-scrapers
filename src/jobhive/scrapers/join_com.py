"""Join.com scraper.

Two-step API: resolve slug → company_id, then fetch company jobs.

    GET https://join.com/companies/{slug}        # returns metadata with id
    GET https://join.com/api/public/companies/{id}/jobs
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from jobhive.exceptions import CompanyNotFoundError, ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

if TYPE_CHECKING:
    from typing import Any

BASE_URL = "https://join.com"
API_BASE = f"{BASE_URL}/api/public"


@ScraperRegistry.register(ATSType.JOIN_COM)
class JoinComScraper(BaseScraper):
    ats = ATSType.JOIN_COM

    def fetch(self) -> list[Job]:
        all_jobs: list[Job] = []
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            company_id = self._resolve_company_id(client)
            page = 1
            while True:
                params = {
                    "locale": "en-us",
                    "page": page,
                    "pageSize": 100,
                    "withAggregations": "true",
                    "sort": "+title",
                }
                try:
                    response = client.get(
                        f"{API_BASE}/companies/{company_id}/jobs", params=params
                    )
                except httpx.HTTPError as exc:
                    raise ScraperError(
                        f"join.com jobs fetch failed for {self.company_slug}: {exc}"
                    ) from exc
                if response.status_code != 200:
                    raise ScraperError(
                        f"join.com returned {response.status_code} listing jobs for "
                        f"{self.company_slug}"
                    )
                payload = response.json()
                items = payload.get("items") or []
                all_jobs.extend(self._parse_job(item) for item in items)
                pagination = payload.get("pagination") or {}
                if page >= pagination.get("totalPages", page):
                    break
                page += 1
        return all_jobs

    def _resolve_company_id(self, client: httpx.Client) -> str:
        try:
            response = client.get(f"{BASE_URL}/companies/{self.company_slug}")
        except httpx.HTTPError as exc:
            raise ScraperError(
                f"join.com company resolve failed for {self.company_slug}: {exc}"
            ) from exc
        if response.status_code == 404:
            raise CompanyNotFoundError(f"join.com company not found: {self.company_slug}")
        # Slug-to-id is exposed via embedded JSON in the page; grep it.
        match = re.search(r'"id"\s*:\s*"?(\d+)"?', response.text)
        if not match:
            raise ScraperError(
                f"join.com page for {self.company_slug} did not expose a company id"
            )
        return match.group(1)

    def _parse_job(self, item: dict[str, Any]) -> Job:
        raw: dict[str, Any] = {}
        for k in ("department", "category", "industry", "skills",
                  "language", "employmentType", "remoteWork"):
            v = item.get(k)
            if v:
                raw[k] = v

        return Job(
            url=item.get("url") or f"{BASE_URL}/companies/{self.company_slug}/jobs/{item['id']}",
            title=item["title"],
            company=self.company_slug,
            ats_type=ATSType.JOIN_COM,
            ats_id=str(item["id"]),
            location=item.get("location") or item.get("city"),
            department=item.get("department") if isinstance(item.get("department"), str) else None,
            commitment=item.get("employmentType") if isinstance(item.get("employmentType"), str) else None,
            posted_at=_parse_iso(item.get("publishedAt") or item.get("createdAt")),
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
