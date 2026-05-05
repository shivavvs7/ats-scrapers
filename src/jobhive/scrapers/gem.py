"""Gem scraper.

Gem job boards live at `https://jobs.gem.com/{slug}` where `{slug}` is the
board ID (kebab-case, no spaces). Jobs are exposed via a public GraphQL
batch endpoint:

    POST https://jobs.gem.com/api/public/graphql/batch

Use the batched `JobBoardList` query, identifying the board by its slug.
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

BASE_URL = "https://jobs.gem.com"
GRAPHQL_URL = f"{BASE_URL}/api/public/graphql/batch"

JOB_BOARD_LIST_QUERY = """
query JobBoardList($boardId: String!) {
  oatsExternalJobPostings(boardId: $boardId) {
    jobPostings {
      id
      extId
      title
      locations { id name city isoCountry isRemote extId __typename }
      job {
        id
        department { id name extId __typename }
        locationType
        employmentType
        __typename
      }
      __typename
    }
    __typename
  }
}
"""


@ScraperRegistry.register(ATSType.GEM)
class GemScraper(BaseScraper):
    """Gem scraper — `company_slug` is the board slug shown in the job-board
    URL (e.g. for `https://jobs.gem.com/accel`, pass `accel`)."""

    ats = ATSType.GEM

    def fetch(self) -> list[Job]:
        payload = [
            {
                "operationName": "JobBoardList",
                "variables": {"boardId": self.company_slug},
                "query": JOB_BOARD_LIST_QUERY,
            }
        ]
        try:
            response = httpx.post(
                GRAPHQL_URL,
                json=payload,
                timeout=self.timeout,
                follow_redirects=True,
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise ScraperError(f"Gem fetch failed for {self.company_slug}: {exc}") from exc
        if response.status_code != 200:
            raise ScraperError(
                f"Gem returned {response.status_code} for {self.company_slug}"
            )
        batch = response.json()
        if not batch:
            return []
        result = batch[0] or {}
        if result.get("errors"):
            raise CompanyNotFoundError(
                f"Gem board not found: {self.company_slug} ({result['errors'][0].get('message')})"
            )
        data = (result.get("data") or {}).get("oatsExternalJobPostings") or {}
        postings = data.get("jobPostings") or []
        return [self._parse_job(item) for item in postings if isinstance(item, dict)]

    def _parse_job(self, item: dict[str, Any]) -> Job:
        ext_id = item.get("extId") or item["id"]

        raw: dict[str, Any] = {}
        for k in ("department", "team", "employmentType",
                  "locations", "remoteType", "salaryRange"):
            v = item.get(k)
            if v:
                raw[k] = v

        return Job(
            url=f"{BASE_URL}/{self.company_slug}/{ext_id}",
            title=item["title"],
            company=self.company_slug,
            ats_type=ATSType.GEM,
            ats_id=str(ext_id),
            location=_extract_location(item.get("locations") or []),
            department=item.get("department") if isinstance(item.get("department"), str) else None,
            commitment=item.get("employmentType") if isinstance(item.get("employmentType"), str) else None,
            requisition_id=item.get("extId") if isinstance(item.get("extId"), str) else None,
            posted_at=None,  # Not exposed in the list endpoint
            fetched_at=datetime.now(),
            raw=raw or None,
        )


def _extract_location(locations: list[dict[str, Any]]) -> str | None:
    if not locations:
        return None
    first = locations[0]
    parts = [first.get("city"), first.get("isoCountry")]
    joined = ", ".join(p for p in parts if p)
    return joined or first.get("name")
