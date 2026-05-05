"""TikTok / Life@TikTok careers scraper.

    POST https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts

Requires `website-path: tiktok` and origin/referer headers; otherwise the
endpoint refuses with 400.
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

API_URL = "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"
PAGE_SIZE = 100

HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US",
    "content-type": "application/json",
    "website-path": "tiktok",
    "origin": "https://lifeattiktok.com",
    "referer": "https://lifeattiktok.com/",
    "user-agent": "Mozilla/5.0",
}


@ScraperRegistry.register(ATSType.TIKTOK)
class TikTokScraper(BaseScraper):
    """TikTok scraper — `company_slug` is informational; jobs are global."""

    ats = ATSType.TIKTOK

    def fetch(self) -> list[Job]:
        all_jobs: list[Job] = []
        offset = 0
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            while True:
                payload = {
                    "limit": PAGE_SIZE,
                    "offset": offset,
                    "keyword": "",
                    "category_id_list": [],
                    "subject_id_list": [],
                    "location_code_list": [],
                    "job_function_id_list": [],
                }
                try:
                    response = client.post(API_URL, json=payload, headers=HEADERS)
                except httpx.HTTPError as exc:
                    raise ScraperError(f"TikTok fetch failed: {exc}") from exc
                if response.status_code != 200:
                    raise ScraperError(f"TikTok returned {response.status_code}: {response.text[:120]}")
                payload_data = response.json().get("data") or {}
                jobs = payload_data.get("job_post_list") or []
                if not jobs:
                    break
                all_jobs.extend(self._parse_job(j) for j in jobs)
                total = payload_data.get("count", 0)
                offset += len(jobs)
                if offset >= total or len(jobs) < PAGE_SIZE:
                    break
        return all_jobs

    def _parse_job(self, item: dict[str, Any]) -> Job:
        ats_id = str(item.get("id") or "")
        post_info = item.get("job_post_info") or {}

        raw: dict[str, Any] = {}
        for k in ("job_category", "job_subcategory", "recruit_type",
                  "experience", "department", "skill_list"):
            v = item.get(k)
            if v:
                raw[k] = v

        return Job(
            url=f"https://lifeattiktok.com/search/{ats_id}",
            title=item.get("title") or item.get("name") or "Untitled",
            company="TikTok",
            ats_type=ATSType.TIKTOK,
            ats_id=ats_id,
            location=_extract_location(item),
            department=item.get("department") if isinstance(item.get("department"), str) else None,
            requisition_id=ats_id if ats_id else None,
            salary_min=_to_float(post_info.get("min_salary")),
            salary_max=_to_float(post_info.get("max_salary")),
            salary_currency=post_info.get("currency"),
            posted_at=_parse_ts(item.get("publish_time") or item.get("post_time")),
            fetched_at=datetime.now(),
            raw=raw or None,
        )


def _extract_location(item: dict) -> str | None:
    """TikTok's `city_info` is a nested location object with parent chain.

    Older API versions used `city_list` (an array); the current API exposes
    a single `city_info` dict whose `parent` chain walks up to country.
    """
    city_info = item.get("city_info")
    if isinstance(city_info, dict):
        parts = []
        node = city_info
        while isinstance(node, dict):
            name = node.get("en_name") or node.get("name")
            if name:
                parts.append(name)
            node = node.get("parent")
        if parts:
            return ", ".join(parts)
    # Legacy: city_list[0].name
    city_list = item.get("city_list") or []
    if city_list and isinstance(city_list[0], dict):
        return city_list[0].get("name")
    return None


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _parse_ts(value: int | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value)
    except (ValueError, OSError):
        return None
