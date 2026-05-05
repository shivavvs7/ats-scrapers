"""BreezyHR careers scraper.

BreezyHR exposes a single public JSON endpoint per tenant:

    GET https://{slug}.breezy.hr/json

Returns ``[{"id":..., "name":..., "location":..., ...}]`` — every position
in one response, no pagination. Each position carries title, location
(structured city/state/country with remote flag), department, salary
range, full-time/part-time type, and the canonical job URL.

Tenants without an active Breezy careers site return a 302 redirect to
``https://breezy.hr/`` (the marketing site) — we treat that as
``CompanyNotFoundError``. Tenants with an active site but zero open
positions return a 200 with ``[]`` (handled cleanly).

Note: BreezyHR's older v3 API (``api.breezy.hr/v3/...``) is OAuth-gated.
This scraper uses only the public unauthenticated endpoint.
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

API_TEMPLATE = "https://{slug}.breezy.hr/json"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.5

_TYPE_MAP = {
    "fullTime": "FULL_TIME",
    "partTime": "PART_TIME",
    "contract": "CONTRACT",
    "intern": "INTERN",
    "internship": "INTERN",
    "temporary": "TEMPORARY",
}


@ScraperRegistry.register(ATSType.BREEZY)
class BreezyScraper(BaseScraper):
    """BreezyHR scraper. ``company_slug`` is the tenant subdomain
    (e.g. ``"fathom"`` → ``https://fathom.breezy.hr/json``)."""

    ats = ATSType.BREEZY

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[Job]:
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=False
        ) as client:
            payload = await self._fetch_with_retry(client)
        if not isinstance(payload, list):
            raise ScraperError(
                f"BreezyHR returned non-list JSON for {self.company_slug}"
            )
        seen: set[str] = set()
        jobs: list[Job] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            job = self._parse_position(item)
            if job is None or job.ats_id in seen:
                continue
            seen.add(job.ats_id)
            jobs.append(job)
        return jobs

    async def _fetch_with_retry(
        self, client: httpx.AsyncClient
    ) -> list[dict[str, Any]]:
        url = API_TEMPLATE.format(slug=self.company_slug)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "application/json",
                    },
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"BreezyHR fetch failed for {self.company_slug}: {exc}"
                    ) from exc
                await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                continue
            if response.status_code in (301, 302, 303, 307, 308):
                # The slug doesn't have an active Breezy careers site —
                # Breezy redirects to its marketing site.
                raise CompanyNotFoundError(
                    f"BreezyHR tenant has no active careers site: {self.company_slug}"
                )
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise ScraperError(
                        f"BreezyHR returned malformed JSON for {self.company_slug}: {exc}"
                    ) from exc
            if response.status_code == 404:
                raise CompanyNotFoundError(
                    f"BreezyHR tenant not found: {self.company_slug}"
                )
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"BreezyHR returned {response.status_code} for "
                        f"{self.company_slug} after {MAX_RETRIES} retries"
                    )
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after) if retry_after and retry_after.isdigit()
                    else RETRY_BASE_DELAY * (2 ** attempt)
                )
                await asyncio.sleep(delay)
                continue
            raise ScraperError(
                f"BreezyHR returned {response.status_code} for {self.company_slug}"
            )
        raise ScraperError(f"BreezyHR exhausted retries for {self.company_slug}")

    def _parse_position(self, item: dict[str, Any]) -> Job | None:
        ats_id = str(item.get("id") or "").strip()
        title = (item.get("name") or "").strip()
        url = item.get("url")
        if not ats_id or not title or not url:
            return None

        type_info = item.get("type")
        type_id = type_info.get("id") if isinstance(type_info, dict) else None
        employment_type = _TYPE_MAP.get(str(type_id), None) if type_id else None

        company_info = item.get("company") or {}
        company_name = (
            company_info.get("name")
            if isinstance(company_info, dict) and company_info.get("name")
            else self.company_slug
        )

        raw: dict[str, Any] = {}
        for k in ("category", "experience", "education", "tags"):
            v = item.get(k)
            if v:
                raw[k] = v

        return Job(
            url=url,
            title=title,
            company=company_name,
            ats_type=ATSType.BREEZY,
            ats_id=ats_id,
            location=_format_location(item.get("location")),
            is_remote=_extract_is_remote(item.get("location")),
            department=item.get("department") or None,
            salary_summary=item.get("salary") or None,
            employment_type=employment_type,
            posted_at=_parse_iso(item.get("published_date")),
            fetched_at=datetime.now(),
            raw=raw or None,
        )


def _format_location(value: object) -> str | None:
    """Breezy's location is structured: ``{"city": ..., "state": {"name": ...},
    "country": {"name": ...}}`` plus a pre-built ``name`` field. Prefer the
    pre-built name when present."""
    if not isinstance(value, dict):
        return None
    name = value.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    parts: list[str] = []
    city = value.get("city")
    if isinstance(city, str) and city.strip():
        parts.append(city.strip())
    state = value.get("state")
    if isinstance(state, dict):
        sn = state.get("name") or state.get("id")
        if isinstance(sn, str) and sn.strip():
            parts.append(sn.strip())
    country = value.get("country")
    if isinstance(country, dict):
        cn = country.get("name")
        if isinstance(cn, str) and cn.strip():
            parts.append(cn.strip())
    return ", ".join(parts) or None


def _extract_is_remote(value: object) -> bool | None:
    if not isinstance(value, dict):
        return None
    flag = value.get("is_remote")
    if isinstance(flag, bool):
        return flag
    return None


def _parse_iso(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
