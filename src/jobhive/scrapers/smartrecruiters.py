"""SmartRecruiters scraper.

Public API:
    https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset=...

Paginated. No auth. Returns rich job objects with location and structured
properties. Salary is rarely present in the list endpoint.
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

API_TEMPLATE = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
PAGE_LIMIT = 100


@ScraperRegistry.register(ATSType.SMARTRECRUITERS)
class SmartRecruitersScraper(BaseScraper):
    ats = ATSType.SMARTRECRUITERS

    def fetch(self) -> list[Job]:
        url = API_TEMPLATE.format(slug=self.company_slug)
        all_jobs: list[Job] = []
        offset = 0
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            while True:
                try:
                    response = client.get(url, params={"limit": PAGE_LIMIT, "offset": offset})
                except httpx.HTTPError as exc:
                    raise ScraperError(
                        f"SmartRecruiters fetch failed for {self.company_slug}: {exc}"
                    ) from exc
                if response.status_code == 404:
                    raise CompanyNotFoundError(
                        f"SmartRecruiters company not found: {self.company_slug}"
                    )
                if response.status_code != 200:
                    raise ScraperError(
                        f"SmartRecruiters returned {response.status_code} for {self.company_slug}"
                    )
                payload = response.json()
                content = payload.get("content", [])
                all_jobs.extend(self._parse_job(item) for item in content)
                if len(content) < PAGE_LIMIT:
                    break
                offset += PAGE_LIMIT
        return all_jobs

    def _parse_job(self, item: dict[str, Any]) -> Job:
        location = item.get("location") or {}
        loc_str = ", ".join(
            part for part in (location.get("city"), location.get("country")) if part
        ) or None
        loc_remote = location.get("remote") if isinstance(location, dict) else None

        department = (item.get("department") or {}).get("label") if isinstance(item.get("department"), dict) else None
        type_of_emp = (item.get("typeOfEmployment") or {}).get("label") if isinstance(item.get("typeOfEmployment"), dict) else None

        is_remote = None
        if isinstance(loc_remote, bool):
            is_remote = loc_remote
        elif location.get("country") == "remote":
            is_remote = True

        raw: dict[str, Any] = {}
        for k in ("industry", "function", "department", "experienceLevel",
                  "creator", "company", "refNumber"):
            v = item.get(k)
            if v:
                raw[k] = v

        return Job(
            url=f"https://jobs.smartrecruiters.com/{self.company_slug}/{item['id']}",
            title=item["name"],
            company=self.company_slug,
            ats_type=ATSType.SMARTRECRUITERS,
            ats_id=item["id"],
            location=loc_str,
            is_remote=is_remote,
            department=department,
            commitment=type_of_emp if isinstance(type_of_emp, str) else None,
            requisition_id=item.get("refNumber") or None,
            posted_at=_parse_iso(item.get("releasedDate")),
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
