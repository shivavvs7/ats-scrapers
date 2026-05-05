"""Personio scraper.

Each Personio tenant is hosted at `{slug}.jobs.personio.com` (or `.com`/`.de`).
Two endpoints work in practice:

    GET https://{slug}.jobs.personio.com/search.json
    GET https://{slug}.jobs.personio.com/api/careers/jobs/list/

The `slug` argument can be either the bare slug or the full base URL.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from jobhive.exceptions import CompanyNotFoundError, ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

if TYPE_CHECKING:
    from typing import Any

ENDPOINTS = ("/search.json", "/api/careers/jobs/list/")


@ScraperRegistry.register(ATSType.PERSONIO)
class PersonioScraper(BaseScraper):
    ats = ATSType.PERSONIO

    def fetch(self) -> list[Job]:
        base = self._resolve_base_url()
        last_error: Exception | None = None
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            for path in ENDPOINTS:
                try:
                    response = client.get(f"{base}{path}")
                except httpx.HTTPError as exc:
                    last_error = exc
                    continue
                if response.status_code == 404:
                    continue
                if response.status_code != 200:
                    last_error = ScraperError(f"Personio returned {response.status_code}")
                    continue
                try:
                    payload = response.json()
                except ValueError:
                    continue
                items = _normalize_items(payload)
                if items:
                    return [self._parse_job(item, base) for item in items]
        if last_error:
            raise CompanyNotFoundError(
                f"Personio tenant {self.company_slug} did not respond on any known endpoint"
            ) from last_error
        return []

    def _resolve_base_url(self) -> str:
        slug = self.company_slug
        if slug.startswith(("http://", "https://")):
            return slug.rstrip("/")
        return f"https://{slug}.jobs.personio.com"

    def _parse_job(self, item: dict[str, Any], base: str) -> Job:
        ats_id = str(item.get("id") or item.get("jobId") or item.get("uuid") or "")
        commitment = item.get("schedule") or item.get("employmentType")

        raw: dict[str, Any] = {}
        for k in ("subcompany", "department", "office", "occupation",
                  "occupationCategory", "seniority", "yearsOfExperience"):
            v = item.get(k)
            if v:
                raw[k] = v

        department = item.get("department")
        if isinstance(department, dict):
            department = department.get("name")

        return Job(
            url=item.get("url") or f"{base}/job/{ats_id}",
            title=item.get("name") or item.get("title") or item.get("subcompany"),
            company=urlparse(base).hostname or self.company_slug,
            ats_type=ATSType.PERSONIO,
            ats_id=ats_id,
            location=_extract_location(item),
            department=department if isinstance(department, str) else None,
            commitment=commitment if isinstance(commitment, str) else None,
            posted_at=_parse_iso(item.get("createdAt") or item.get("created_at")),
            fetched_at=datetime.now(),
            raw=raw or None,
        )


def _normalize_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("data", "jobs", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [p for p in value if isinstance(p, dict)]
    return []


def _extract_location(item: dict[str, Any]) -> str | None:
    if isinstance(item.get("office"), str):
        return item["office"]
    loc = item.get("location") or item.get("office") or {}
    if isinstance(loc, str):
        return loc
    if isinstance(loc, dict):
        return loc.get("name") or loc.get("city")
    return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
