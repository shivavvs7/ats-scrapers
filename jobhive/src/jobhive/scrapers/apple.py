"""Apple careers scraper.

Apple's job board requires a CSRF token before search calls succeed:

    1. GET https://jobs.apple.com/api/v1/CSRFToken     # cookie + header set
    2. POST https://jobs.apple.com/api/v1/jobsTeam     # search payload

The CSRF flow is held in a single httpx.Client session.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from jobhive.exceptions import ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

if TYPE_CHECKING:
    from typing import Any

BASE_URL = "https://jobs.apple.com"
CSRF_URL = f"{BASE_URL}/api/v1/CSRFToken"
SEARCH_URL = f"{BASE_URL}/api/v1/search"
PAGE_SIZE = 20


@ScraperRegistry.register(ATSType.APPLE)
class AppleScraper(BaseScraper):
    """Apple scraper — `company_slug` is informational; jobs are global."""

    ats = ATSType.APPLE

    def fetch(self) -> list[Job]:
        all_jobs: list[Job] = []
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            client.headers.update(
                {
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                    "Origin": BASE_URL,
                    "Referer": f"{BASE_URL}/en-us/search",
                }
            )
            try:
                csrf_response = client.get(CSRF_URL)
            except httpx.HTTPError as exc:
                raise ScraperError(f"Apple CSRF fetch failed: {exc}") from exc
            if csrf_response.status_code != 200:
                raise ScraperError(
                    f"Apple CSRF endpoint returned {csrf_response.status_code}"
                )
            csrf_token = csrf_response.headers.get("x-apple-csrf-token")
            if not csrf_token:
                raise ScraperError("Apple did not return an x-apple-csrf-token header")
            client.headers["X-Apple-CSRF-Token"] = csrf_token

            page = 1
            while True:
                payload = {
                    "query": "",
                    "filters": {},
                    "page": page,
                    "locale": "en-us",
                    "sort": "",
                    "format": {
                        "longDate": "MMMM D, YYYY",
                        "mediumDate": "MMM D, YYYY",
                    },
                }
                try:
                    response = client.post(SEARCH_URL, json=payload)
                except httpx.HTTPError as exc:
                    raise ScraperError(f"Apple search failed: {exc}") from exc
                if response.status_code != 200:
                    raise ScraperError(
                        f"Apple search returned {response.status_code}: {response.text[:120]}"
                    )
                data = response.json()
                postings = (data.get("res") or {}).get("searchResults") or []
                if not postings:
                    break
                all_jobs.extend(self._parse_job(p) for p in postings)
                total = (data.get("res") or {}).get("totalRecords", 0)
                if page * PAGE_SIZE >= total or len(postings) < PAGE_SIZE:
                    break
                page += 1
        return all_jobs

    def _parse_job(self, item: dict[str, Any]) -> Job:
        position_id = str(item.get("positionId") or item.get("id") or "")
        slug = item.get("transformedPostingTitle") or item.get("titleSlug") or "role"

        raw: dict[str, Any] = {}
        for k in ("team", "managedPipelineRole", "homeOffice",
                  "jobSummary", "minimumQualifications"):
            v = item.get(k)
            if v:
                raw[k] = v

        return Job(
            url=f"{BASE_URL}/en-us/details/{position_id}/{slug}",
            title=item.get("postingTitle") or item.get("title") or "Untitled",
            company="Apple",
            ats_type=ATSType.APPLE,
            ats_id=position_id,
            location=_format_locations(item),
            team=item.get("team") if isinstance(item.get("team"), str) else None,
            requisition_id=position_id if position_id else None,
            posted_at=_parse_iso(item.get("postingDate") or item.get("postDate")),
            fetched_at=datetime.now(),
            raw=raw or None,
        )


def _format_locations(item: dict[str, Any]) -> str | None:
    locs = item.get("locations") or item.get("locationsList") or []
    if isinstance(locs, list) and locs:
        first = locs[0]
        if isinstance(first, dict):
            return first.get("name") or first.get("city")
        return str(first)
    if isinstance(item.get("location"), str):
        return item["location"]
    return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
