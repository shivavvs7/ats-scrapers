"""Workable scraper.

Public widget API:
    https://apply.workable.com/api/v1/widget/accounts/{slug}

Returns a single JSON payload with ``jobs[]``. No auth.

Workable rate-limits hard from a single IP — bulk pipeline runs at
concurrency >2 see 429s on most tenants. The scraper retries 429/5xx
with exponential backoff (honouring ``Retry-After`` when present); the
caller should still keep concurrency low (2-4) for full re-scrapes.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from jobhive.exceptions import CompanyNotFoundError, ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

if TYPE_CHECKING:
    from typing import Any

API_TEMPLATE = "https://apply.workable.com/api/v1/widget/accounts/{slug}"
MAX_RETRIES = 4
RETRY_BASE_DELAY = 1.5
USER_AGENT = "Mozilla/5.0 (compatible; jobhive/1.0)"


@ScraperRegistry.register(ATSType.WORKABLE)
class WorkableScraper(BaseScraper):
    ats = ATSType.WORKABLE

    def fetch(self) -> list[Job]:
        url = API_TEMPLATE.format(slug=self.company_slug)
        response = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = httpx.get(
                    url,
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Workable fetch failed for {self.company_slug}: {exc}"
                    ) from exc
                time.sleep(RETRY_BASE_DELAY * attempt)
                continue
            if response.status_code == 404:
                raise CompanyNotFoundError(
                    f"Workable account not found: {self.company_slug}"
                )
            if response.status_code == 200:
                break
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Workable returned {response.status_code} for "
                        f"{self.company_slug} after {MAX_RETRIES} attempts"
                    )
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.replace(".", "").isdigit()
                    else RETRY_BASE_DELAY * (2 ** attempt)
                )
                time.sleep(delay)
                continue
            raise ScraperError(
                f"Workable returned {response.status_code} for {self.company_slug}"
            )
        if response is None or response.status_code != 200:
            raise ScraperError(
                f"Workable exhausted retries for {self.company_slug}"
            )

        payload = response.json()
        return [self._parse_job(item) for item in payload.get("jobs", [])]

    def _parse_job(self, item: dict[str, Any]) -> Job:
        url = item.get("url") or item.get("application_url")
        apply_url = item.get("application_url")
        # Workable's "type" mirrors employment shape (full-time, contract, etc.)
        commitment = item.get("type") or item.get("employment_type")

        is_remote = None
        if isinstance(item.get("telecommuting"), bool):
            is_remote = item["telecommuting"]
        elif isinstance(item.get("remote"), bool):
            is_remote = item["remote"]

        raw: dict[str, Any] = {}
        for k in ("department", "function", "industry", "experience",
                  "education", "language", "locations"):
            v = item.get(k)
            if v:
                raw[k] = v

        return Job(
            url=url,
            title=item["title"],
            company=self.company_slug,
            ats_type=ATSType.WORKABLE,
            ats_id=item.get("shortcode") or item.get("code") or str(item.get("id", "")),
            location=_extract_location(item),
            is_remote=is_remote,
            department=item.get("department") if isinstance(item.get("department"), str) else None,
            commitment=commitment if isinstance(commitment, str) else None,
            apply_url=apply_url if isinstance(apply_url, str) and apply_url != url else None,
            posted_at=_parse_iso(item.get("published_on") or item.get("created_at")),
            fetched_at=datetime.now(),
            raw=raw or None,
        )


def _extract_location(item: dict[str, Any]) -> str | None:
    """Workable exposes location two ways:
    - flat fields `city`, `state`, `country` at the top level
    - structured `locations` array of dicts (more recent API)
    `location: {city, region, country}` shows up in the widget payload too.
    Try the richest representation first.
    """
    locs = item.get("locations") or []
    if isinstance(locs, list) and locs:
        first = locs[0] if isinstance(locs[0], dict) else {}
        parts = [first.get("city"), first.get("region"), first.get("country")]
        joined = ", ".join(p for p in parts if p)
        if joined:
            return joined
    nested = item.get("location") or {}
    if isinstance(nested, dict) and nested:
        parts = [nested.get("city"), nested.get("region"), nested.get("country")]
        joined = ", ".join(p for p in parts if p)
        if joined:
            return joined
    parts = [item.get("city"), item.get("state"), item.get("country")]
    return ", ".join(p for p in parts if p) or None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
