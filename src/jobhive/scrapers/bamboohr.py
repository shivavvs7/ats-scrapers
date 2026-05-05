"""BambooHR scraper.

BambooHR's old `/careers/list` JSON endpoint was deprecated in 2024 — every
tenant now serves a 404 there. The current public source of truth is the
embedded careers widget at `/jobs/embed2.php`, which renders all open jobs
as static HTML grouped by department:

    GET https://{slug}.bamboohr.com/jobs/embed2.php

Widget structure (one block per department, one `<li>` per job):

    <li id="bhrDepartmentID_{dept_id}" class="BambooHR-ATS-Department-Item">
      <div id="department_{dept_id}" class="BambooHR-ATS-Department-Header">
        {Department}
      </div>
      <ul class="BambooHR-ATS-Jobs-List">
        <li id="bhrPositionID_{job_id}" class="BambooHR-ATS-Jobs-Item">
          <a href="//{slug}.bamboohr.com/careers/{job_id}">{Title}</a>
          <span class="BambooHR-ATS-Location">{City, State}</span>
        </li>
      </ul>
    </li>

Tenants without open jobs return a 200 with an empty widget (~270 bytes).
For descriptions, hit `/careers/{job_id}` (HTML) — opt in via
`fetch_descriptions=True`.
"""

from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime
from typing import TYPE_CHECKING

import httpx

from jobhive.exceptions import CompanyNotFoundError, ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

if TYPE_CHECKING:
    pass

WIDGET_TEMPLATE = "https://{slug}.bamboohr.com/jobs/embed2.php"
DETAIL_TEMPLATE = "https://{slug}.bamboohr.com/careers/{id}"

MAX_CONCURRENCY = 8
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.5

# Each department block is wrapped in a <li class="BambooHR-ATS-Department-Item">.
# Inside, the header div carries the department name and the <ul> holds jobs.
_DEPARTMENT_BLOCK_RE = re.compile(
    r'<li id="bhrDepartmentID_(?P<dept_id>\d+)"[^>]*'
    r'class="BambooHR-ATS-Department-Item"[^>]*>'
    r'(?P<body>.*?)'
    r'(?=<li id="bhrDepartmentID_|\Z)',
    re.DOTALL | re.IGNORECASE,
)
_DEPARTMENT_NAME_RE = re.compile(
    r'<div[^>]*class="BambooHR-ATS-Department-Header"[^>]*>\s*(?P<name>[^<]+?)\s*</div>',
    re.DOTALL | re.IGNORECASE,
)
_POSITION_RE = re.compile(
    r'<li id="bhrPositionID_(?P<id>\d+)"[^>]*'
    r'class="BambooHR-ATS-Jobs-Item"[^>]*>'
    r'(?P<body>.*?)</li>',
    re.DOTALL | re.IGNORECASE,
)
_POSITION_LINK_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>\s*(?P<title>.*?)\s*</a>',
    re.DOTALL | re.IGNORECASE,
)
_POSITION_LOCATION_RE = re.compile(
    r'<span[^>]*class="BambooHR-ATS-Location"[^>]*>\s*(?P<loc>[^<]+?)\s*</span>',
    re.IGNORECASE,
)
# /careers/{id} detail page: description lives in a div with this class
_DETAIL_DESCRIPTION_RE = re.compile(
    r'<div[^>]*class="(?:[^"]*\b)?BambooHR-ATS-Description\b[^"]*"[^>]*>\s*(?P<body>.*?)\s*</div>\s*(?:<div|<footer|</body)',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


@ScraperRegistry.register(ATSType.BAMBOOHR)
class BambooHRScraper(BaseScraper):
    """BambooHR scraper — `company_slug` is the tenant subdomain.

    `fetch_descriptions=True` fetches the per-job HTML page in parallel
    (slow, capped at MAX_CONCURRENCY). Off by default to stay polite and fast."""

    ats = ATSType.BAMBOOHR

    def __init__(
        self,
        company_slug: str,
        *,
        timeout: float = 30.0,
        fetch_descriptions: bool = False,
    ) -> None:
        super().__init__(company_slug, timeout=timeout)
        self.fetch_descriptions = fetch_descriptions

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[Job]:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=MAX_CONCURRENCY * 2,
                max_keepalive_connections=MAX_CONCURRENCY,
            ),
        ) as client:
            html = await self._fetch_widget(client)
            jobs = self._parse_widget(html)
            if self.fetch_descriptions and jobs:
                await self._enrich_descriptions(client, jobs)
            return jobs

    async def _fetch_widget(self, client: httpx.AsyncClient) -> str:
        url = WIDGET_TEMPLATE.format(slug=self.company_slug)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(
                    url, headers={"User-Agent": "Mozilla/5.0"}
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"BambooHR fetch failed for {self.company_slug}: {exc}"
                    ) from exc
                await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                continue
            if response.status_code == 404:
                raise CompanyNotFoundError(
                    f"BambooHR tenant not found: {self.company_slug}"
                )
            if response.status_code == 200:
                return response.text
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"BambooHR ({self.company_slug}) returned "
                        f"{response.status_code} after {MAX_RETRIES} retries"
                    )
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after) if retry_after and retry_after.isdigit()
                    else RETRY_BASE_DELAY * (2 ** attempt)
                )
                await asyncio.sleep(delay)
                continue
            raise ScraperError(
                f"BambooHR ({self.company_slug}) returned {response.status_code}"
            )
        raise ScraperError(
            f"BambooHR ({self.company_slug}) exhausted retries"
        )

    def _parse_widget(self, html: str) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()
        # Walk department blocks so each job inherits its department name.
        # Some legacy tenants render jobs without a wrapping department —
        # handle those by also scanning the document tail.
        consumed_end = 0
        for dept_match in _DEPARTMENT_BLOCK_RE.finditer(html):
            consumed_end = dept_match.end()
            dept_body = dept_match.group("body")
            dept_name_match = _DEPARTMENT_NAME_RE.search(dept_body)
            dept_name = (
                _strip_tags(dept_name_match.group("name"))
                if dept_name_match
                else None
            )
            for position_match in _POSITION_RE.finditer(dept_body):
                job = self._parse_position(
                    position_match.group("id"),
                    position_match.group("body"),
                    department=dept_name,
                )
                if job is None or job.ats_id in seen:
                    continue
                seen.add(job.ats_id)
                jobs.append(job)
        # Stragglers outside any department block.
        for position_match in _POSITION_RE.finditer(html, pos=consumed_end):
            job = self._parse_position(
                position_match.group("id"),
                position_match.group("body"),
                department=None,
            )
            if job is None or job.ats_id in seen:
                continue
            seen.add(job.ats_id)
            jobs.append(job)
        return jobs

    def _parse_position(
        self, ats_id: str, body: str, *, department: str | None
    ) -> Job | None:
        link = _POSITION_LINK_RE.search(body)
        if not link:
            return None
        title = _strip_tags(link.group("title"))
        if not title:
            return None
        href = link.group("href").strip()
        url = href if href.startswith("http") else (
            f"https:{href}" if href.startswith("//")
            else f"https://{self.company_slug}.bamboohr.com{href}"
        )
        loc_match = _POSITION_LOCATION_RE.search(body)
        location = loc_match.group("loc").strip() if loc_match else None
        return Job(
            url=url,
            title=title,
            company=self.company_slug,
            ats_type=ATSType.BAMBOOHR,
            ats_id=ats_id,
            location=location,
            department=department,
            posted_at=None,
            fetched_at=datetime.now(),
        )

    async def _enrich_descriptions(
        self, client: httpx.AsyncClient, jobs: list[Job]
    ) -> None:
        sem = asyncio.Semaphore(MAX_CONCURRENCY)

        async def task(job: Job) -> None:
            async with sem:
                description = await self._fetch_description(client, job.ats_id)
            if description is not None:
                # Job is frozen via `model_config = ConfigDict(populate_by_name=True)`,
                # not `frozen=True` — direct attribute set works.
                job.description = description[:10_000]  # type: ignore[misc]

        await asyncio.gather(*(task(j) for j in jobs))

    async def _fetch_description(
        self, client: httpx.AsyncClient, job_id: str
    ) -> str | None:
        url = DETAIL_TEMPLATE.format(slug=self.company_slug, id=job_id)
        try:
            response = await client.get(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        match = _DETAIL_DESCRIPTION_RE.search(response.text)
        if not match:
            return None
        return _strip_tags(match.group("body")).strip() or None


def _strip_tags(text: str) -> str:
    """Tiny HTML→text helper. We control the markup (BambooHR widgets), so
    we don't need a full parser — strip tags, decode entities, collapse
    whitespace."""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()
