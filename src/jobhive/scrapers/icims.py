"""iCIMS Talent Cloud careers scraper.

Used by Disney, Kroger, AT&T, Visa, Peraton, Audacy, Vioc, and many others.

iCIMS career sites are HTML only — no public JSON. Each tenant lives on
``careers-{slug}.icims.com`` (sometimes ``uscareers-{slug}.icims.com``). The
visible careers page embeds an iframe with the actual job listings; we hit
the iframe URL directly to skip the wrapper:

    GET https://careers-{slug}.icims.com/jobs/search?ss=1&pr={page}&in_iframe=1

Job entries look like:

    <a href="https://careers-{slug}.icims.com/jobs/{id}/{title-slug}/job?in_iframe=1"
       class="iCIMS_Anchor">
      <h3>Title</h3>
    </a>
    <span title="4/30/2026 10:11 PM">3 days ago</span>
    <div class="description">summary text...</div>

Pagination via ``pr={N}``, 0-indexed. Each page typically holds 25 jobs.
We paginate until a page yields no new IDs.
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

MAX_PAGES = 200  # Safety bound; iCIMS tenants rarely exceed 5K jobs.
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.5

# Each job is wrapped in an `<a class="iCIMS_Anchor"... href="...">` with a
# nested `<h3>` containing the title.
_JOB_ANCHOR_RE = re.compile(
    r'<a[^>]+href="(?P<href>https?://[^"]*?/jobs/(?P<id>\d+)/[^"]*?/job[^"]*)"[^>]*'
    r'class="iCIMS_Anchor"[^>]*>'
    r'(?P<inner>.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_TITLE_RE = re.compile(r'<h3[^>]*>(?P<title>.*?)</h3>', re.DOTALL | re.IGNORECASE)
_DATE_TITLE_RE = re.compile(
    r'<span[^>]+title="(?P<date>[\d/]+\s+[\d:]+\s*(?:AM|PM)?)"',
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


@ScraperRegistry.register(ATSType.ICIMS)
class iCIMSScraper(BaseScraper):  # noqa: N801  matches public iCIMS branding
    """iCIMS scraper. ``company_slug`` is either:

    - A bare slug — ``"peraton"`` → ``https://careers-peraton.icims.com``
    - A full URL — ``"https://uscareers-rws.icims.com"`` (for the
      ``uscareers-`` variant or any custom subdomain)
    """

    ats = ATSType.ICIMS

    def __init__(
        self,
        company_slug: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        super().__init__(company_slug, timeout=timeout)
        self.base_url = self._resolve_base_url(company_slug)

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[Job]:
        seen: set[str] = set()
        all_jobs: list[Job] = []
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            for page_num in range(MAX_PAGES):
                html_text = await self._fetch_page(client, page=page_num)
                page_jobs = self._parse_page(html_text)
                new = [j for j in page_jobs if j.ats_id not in seen]
                if not new:
                    break
                for j in new:
                    seen.add(j.ats_id)
                all_jobs.extend(new)
        return all_jobs

    def _resolve_base_url(self, slug: str) -> str:
        if slug.startswith(("http://", "https://")):
            return slug.rstrip("/")
        return f"https://careers-{slug}.icims.com"

    async def _fetch_page(
        self, client: httpx.AsyncClient, *, page: int
    ) -> str:
        url = f"{self.base_url}/jobs/search"
        params = {"ss": "1", "pr": page, "in_iframe": "1"}
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(
                    url,
                    params=params,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"iCIMS fetch failed for {self.base_url} at page={page}: {exc}"
                    ) from exc
                await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                continue
            if response.status_code == 404:
                raise CompanyNotFoundError(
                    f"iCIMS site not found: {self.base_url}"
                )
            if response.status_code == 200:
                return response.text
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"iCIMS returned {response.status_code} for "
                        f"{self.base_url} at page={page} after {MAX_RETRIES} retries"
                    )
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after) if retry_after and retry_after.isdigit()
                    else RETRY_BASE_DELAY * (2 ** attempt)
                )
                await asyncio.sleep(delay)
                continue
            raise ScraperError(
                f"iCIMS returned {response.status_code} for {self.base_url} "
                f"at page={page}"
            )
        raise ScraperError(
            f"iCIMS exhausted retries for {self.base_url} at page={page}"
        )

    def _parse_page(self, html_text: str) -> list[Job]:
        jobs: list[Job] = []
        seen_in_page: set[str] = set()
        company = self._company_name()
        for match in _JOB_ANCHOR_RE.finditer(html_text):
            ats_id = match.group("id")
            if ats_id in seen_in_page:
                # iCIMS sometimes renders multiple anchors per job (title +
                # icon link); dedup within the page so cross-page logic
                # gets clean input.
                continue
            seen_in_page.add(ats_id)
            href = html.unescape(match.group("href"))
            inner = match.group("inner")
            title_match = _TITLE_RE.search(inner)
            if not title_match:
                continue
            title = _strip(title_match.group("title"))
            if not title:
                continue
            jobs.append(
                Job(
                    url=href,
                    title=title,
                    company=company,
                    ats_type=ATSType.ICIMS,
                    ats_id=ats_id,
                    location=None,  # iCIMS HTML rarely surfaces location in the
                                    # listing — would need per-job page fetch.
                    posted_at=None,
                    fetched_at=datetime.now(),
                )
            )
        return jobs

    def _company_name(self) -> str:
        # `careers-peraton.icims.com` → `peraton`
        # `uscareers-rws.icims.com` → `rws`
        host = self.base_url.replace("https://", "").replace("http://", "")
        host = host.split("/", 1)[0]
        if host.startswith("careers-"):
            return host.removeprefix("careers-").split(".", 1)[0]
        if host.startswith("uscareers-"):
            return host.removeprefix("uscareers-").split(".", 1)[0]
        return host.split(".", 1)[0]


def _strip(text: str) -> str:
    """Strip tags + entities + collapse whitespace from inner HTML."""
    cleaned = _TAG_RE.sub(" ", text)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
