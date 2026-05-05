"""Oracle HCM Cloud scraper.

⚠️  EXPERIMENTAL — the Oracle Recruiting Cloud REST API wraps job results in
a `requisitionList` envelope whose exact path varies per tenant. Title,
location, and posted-date field names also differ across versions. The basic
flow below works for many tenants but not all. For production-grade
reliability, fall back to the legacy `oracle/main.py` until 0.2.0.

Oracle Recruiting Cloud sites live at:
    https://{subdomain}.fa.{region}.oraclecloud.com/hcmUI/CandidateExperience/...

The unauthenticated REST endpoint:
    GET {base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
        ?onlyData=true&limit=200&offset=0&finder=findReqs;siteNumber={site}

Pass the full base URL (and optionally a site number) as the slug.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from jobhive.exceptions import CompanyNotFoundError, ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

if TYPE_CHECKING:
    from typing import Any

PAGE_LIMIT = 200
SITE_RE = re.compile(r"site_number=([^&]+)")
DEFAULT_SITE = "CX_1"
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.5


@ScraperRegistry.register(ATSType.ORACLE)
class OracleScraper(BaseScraper):
    """Oracle scraper — `company_slug` is the full careers URL.

    Optionally append `?site_number=CX_xxxxx` to the URL to target a specific
    Oracle careers site within the tenant.
    """

    ats = ATSType.ORACLE

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[Job]:
        url = self.company_slug
        match = SITE_RE.search(url)
        site = match.group(1) if match else DEFAULT_SITE
        base = url.split("?", 1)[0].rstrip("/")
        if not base.startswith(("http://", "https://")):
            raise ScraperError(
                f"Oracle slug must be a full URL (https://...oraclecloud.com), got {base!r}"
            )
        api = f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

        all_jobs: list[Job] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            # First call also tells us TotalJobsCount.
            first = await self._fetch_with_retry(client, api, base, site, offset=0)
            items, total = _unwrap(first)
            for it in items:
                job = self._parse_job(it, base, site)
                if job.ats_id and job.ats_id not in seen:
                    seen.add(job.ats_id)
                    all_jobs.append(job)
            if total is None or total <= len(items):
                return all_jobs

            # Paginate the rest. Use `len(items)` as the actual page size
            # (Oracle may return less than the requested limit on the first
            # page, e.g. 198 instead of 200).
            page_size = max(len(items), 1)
            offsets = list(range(page_size, total, page_size))
            for offset in offsets:
                payload = await self._fetch_with_retry(
                    client, api, base, site, offset=offset
                )
                page_items, _ = _unwrap(payload)
                if not page_items:
                    break
                for it in page_items:
                    job = self._parse_job(it, base, site)
                    if job.ats_id and job.ats_id not in seen:
                        seen.add(job.ats_id)
                        all_jobs.append(job)
        return all_jobs

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        api: str,
        base: str,
        site: str,
        offset: int,
    ) -> dict[str, Any]:
        params = {
            "onlyData": "true",
            # Pagination params MUST live inside the `finder` string —
            # Oracle silently ignores top-level `limit`/`offset` and returns
            # a fixed 25 results from the first page when they're external.
            "finder": f"findReqs;siteNumber={site},limit={PAGE_LIMIT},offset={offset}",
            # Without `expand=requisitionList`, the response only contains
            # search-context metadata (facets, totalCount), not actual jobs.
            "expand": "requisitionList",
        }
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(
                    api, params=params, headers={"Accept": "application/json"},
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Oracle fetch failed for {base} at offset={offset}: {exc}"
                    ) from exc
                await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                continue
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                raise CompanyNotFoundError(f"Oracle careers site not found: {base}")
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Oracle ({base}) returned {response.status_code} at "
                        f"offset={offset} after {MAX_RETRIES} retries"
                    )
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after) if retry_after and retry_after.isdigit()
                    else RETRY_BASE_DELAY * (2 ** attempt)
                )
                await asyncio.sleep(delay)
                continue
            raise ScraperError(
                f"Oracle returned {response.status_code} for {base} at offset={offset}"
            )
        raise ScraperError(f"Oracle ({base}) exhausted retries at offset={offset}")

    def _parse_job(self, item: dict[str, Any], base: str, site: str) -> Job:
        ats_id = str(item.get("Id") or item.get("RequisitionNumber") or "")
        company = urlparse(base).hostname or self.company_slug
        title = item.get("Title") or "Untitled"

        raw: dict[str, Any] = {}
        for k in ("Category", "JobFamilyName", "WorkLocation",
                  "WorkerCategory", "OrganizationName", "BusinessUnitName",
                  "JobFunctionName", "PrimaryLocationCountry"):
            v = item.get(k)
            if v:
                raw[k] = v

        return Job(
            url=item.get("ExternalURL")
            or f"{base}/?keyword=&mode=jobs&lang=en&site_number={site}#{ats_id}",
            title=title,
            company=company,
            ats_type=ATSType.ORACLE,
            ats_id=ats_id,
            location=item.get("PrimaryLocation"),
            department=item.get("OrganizationName") if isinstance(item.get("OrganizationName"), str) else None,
            commitment=item.get("WorkerCategory") if isinstance(item.get("WorkerCategory"), str) else None,
            requisition_id=item.get("RequisitionNumber") if isinstance(item.get("RequisitionNumber"), str) else None,
            posted_at=_parse_iso(item.get("PostedDate") or item.get("CreatedOn")),
            fetched_at=datetime.now(),
            raw=raw or None,
        )


def _unwrap(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    """Pull ``(requisitions, totalJobsCount)`` from Oracle's response.

    Oracle wraps the actual list at ``items[0].requisitionList`` and exposes
    the real total at ``items[0].TotalJobsCount``. Without ``expand=requisitionList``
    the inner list is missing entirely (only facet metadata returns).
    """
    items = payload.get("items") or []
    if not items or not isinstance(items[0], dict):
        return [], None
    item0 = items[0]
    reqs = item0.get("requisitionList")
    if not isinstance(reqs, list):
        return [], item0.get("TotalJobsCount")
    return reqs, item0.get("TotalJobsCount")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
