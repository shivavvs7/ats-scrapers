"""Rippling ATS scraper.

Public board API:
    https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from jobhive.exceptions import CompanyNotFoundError, ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

if TYPE_CHECKING:
    from typing import Any

API_TEMPLATE = "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs"


@ScraperRegistry.register(ATSType.RIPPLING)
class RipplingScraper(BaseScraper):
    ats = ATSType.RIPPLING

    def fetch(self) -> list[Job]:
        url = API_TEMPLATE.format(slug=self.company_slug)
        try:
            response = httpx.get(
                url,
                timeout=self.timeout,
                follow_redirects=True,
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise ScraperError(f"Rippling fetch failed for {self.company_slug}: {exc}") from exc
        if response.status_code == 404:
            raise CompanyNotFoundError(f"Rippling board not found: {self.company_slug}")
        if response.status_code != 200:
            raise ScraperError(
                f"Rippling returned {response.status_code} for {self.company_slug}"
            )

        payload = response.json()
        if isinstance(payload, dict):
            items = payload.get("items") or payload.get("jobs") or []
        elif isinstance(payload, list):
            items = payload
        else:
            items = []
        return [self._parse_job(item) for item in items]

    def _parse_job(self, item: dict[str, Any]) -> Job:
        raw: dict[str, Any] = {}
        for k in ("department", "team", "employmentType",
                  "workType", "experienceLevel", "compensation"):
            v = item.get(k)
            if v:
                raw[k] = v

        return Job(
            url=item.get("url") or item.get("hostedUrl") or f"https://ats.rippling.com/{self.company_slug}/jobs/{item.get('id')}",
            title=item["name"] if "name" in item else item["title"],
            company=self.company_slug,
            ats_type=ATSType.RIPPLING,
            ats_id=str(item.get("id") or item.get("uuid") or ""),
            location=_extract_location(item),
            department=item.get("department") if isinstance(item.get("department"), str) else None,
            commitment=item.get("employmentType") if isinstance(item.get("employmentType"), str) else None,
            posted_at=_parse_iso(item.get("createdAt") or item.get("created_at")),
            fetched_at=datetime.now(),
            raw=raw or None,
        )


def _extract_location(item: dict[str, Any]) -> str | None:
    loc = item.get("workLocation") or item.get("location") or {}
    if isinstance(loc, str):
        return loc
    if isinstance(loc, dict):
        return loc.get("displayName") or loc.get("city") or loc.get("country")
    return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
