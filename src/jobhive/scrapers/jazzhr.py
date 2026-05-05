"""JazzHR scraper.

JazzHR ("applytojob.com") has no public JSON API — every tenant serves a
single HTML listing page at:

    GET https://{slug}.applytojob.com/apply/jobs

All open jobs are rendered in one server-side table, no pagination. Each
row looks like:

    <tr id="row_job_..." class="resumator_even_row">
      <td>
        <a class="job_title_link" href="/apply/jobs/details/{id}?&">{Title}</a>
        <br /><span class="resumator_department">{Department}</span>
      </td>
      <td>{Location}</td>
    </tr>

Some JazzHR tenants sit behind Cloudflare and 403 plain httpx. ``client_kind``
follows the same pattern as the Eightfold scraper:

- ``"auto"`` (default): try httpx first, fall back to httpcloak on 403.
- ``"httpx"``: pinned httpx, surface 403 as an error.
- ``"httpcloak"``: skip the probe, go straight to httpcloak.
"""

from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime
from typing import TYPE_CHECKING, Literal

import httpx

from jobhive.exceptions import CompanyNotFoundError, ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

if TYPE_CHECKING:
    pass

LISTING_TEMPLATE = "https://{slug}.applytojob.com/apply/jobs"
JOB_URL_TEMPLATE = "https://{slug}.applytojob.com/apply/jobs/details/{id}"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.5

ClientKind = Literal["auto", "httpx", "httpcloak"]


# Each table row that wraps a single job. Captures everything between the
# opening <tr> and its closing </tr>.
_ROW_RE = re.compile(
    r'<tr\s+id="row_job_[^"]+"[^>]*>(?P<body>.*?)</tr>',
    re.DOTALL | re.IGNORECASE,
)
_TITLE_RE = re.compile(
    # JazzHR IDs are typically 10-char alphanumeric (e.g. `ep3PtoGGEJ`),
    # but we accept underscores/hyphens defensively in case a tenant uses
    # a non-standard scheme.
    r'<a[^>]+class="[^"]*job_title_link[^"]*"[^>]+'
    r'href="/apply/jobs/details/(?P<id>[A-Za-z0-9_-]+)[^"]*"[^>]*>'
    r'(?P<title>.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_DEPT_RE = re.compile(
    r'<span[^>]*class="[^"]*resumator_department[^"]*"[^>]*>'
    r'(?P<dept>.*?)</span>',
    re.DOTALL | re.IGNORECASE,
)
# Location lives in the SECOND <td> of the row — naive: take the last <td>.
_LAST_TD_RE = re.compile(r'<td[^>]*>(?P<body>(?:(?!<td).)*?)</td>\s*$', re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


@ScraperRegistry.register(ATSType.JAZZHR)
class JazzHRScraper(BaseScraper):
    """JazzHR scraper — `company_slug` is the tenant subdomain."""

    ats = ATSType.JAZZHR

    def __init__(
        self,
        company_slug: str,
        *,
        timeout: float = 30.0,
        client_kind: ClientKind = "auto",
    ) -> None:
        super().__init__(company_slug, timeout=timeout)
        self.client_kind: ClientKind = client_kind

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[Job]:
        if self.client_kind == "httpcloak":
            html_text = await asyncio.to_thread(self._fetch_via_httpcloak_sync)
            return self._parse_listing(html_text)

        # httpx or auto: try httpx first
        try:
            html_text = await self._fetch_via_httpx()
        except _WAFBlocked as exc:
            if self.client_kind == "httpx":
                raise ScraperError(
                    f"JazzHR ({self.company_slug}) blocked by WAF (403); "
                    f"set client_kind='httpcloak' to bypass"
                ) from exc
            html_text = await asyncio.to_thread(self._fetch_via_httpcloak_sync)
        return self._parse_listing(html_text)

    # --- httpx path -----------------------------------------------------

    async def _fetch_via_httpx(self) -> str:
        url = LISTING_TEMPLATE.format(slug=self.company_slug)
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    response = await client.get(
                        url, headers={"User-Agent": "Mozilla/5.0"}
                    )
                except httpx.HTTPError as exc:
                    if attempt == MAX_RETRIES:
                        raise ScraperError(
                            f"JazzHR fetch failed for {self.company_slug}: {exc}"
                        ) from exc
                    await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                    continue
                if response.status_code == 404:
                    raise CompanyNotFoundError(
                        f"JazzHR tenant not found: {self.company_slug}"
                    )
                if response.status_code == 403:
                    raise _WAFBlocked()
                if response.status_code == 200:
                    return response.text
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if attempt == MAX_RETRIES:
                        raise ScraperError(
                            f"JazzHR ({self.company_slug}) returned "
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
                    f"JazzHR ({self.company_slug}) returned {response.status_code}"
                )
        raise ScraperError(f"JazzHR ({self.company_slug}) exhausted retries")

    # --- httpcloak path -------------------------------------------------

    def _fetch_via_httpcloak_sync(self) -> str:
        try:
            import httpcloak  # noqa: F401
        except ImportError as exc:
            raise ScraperError(
                "httpcloak required for this tenant; install with "
                "`pip install httpcloak`"
            ) from exc
        return self._fetch_page_httpcloak()

    def _fetch_page_httpcloak(self) -> str:
        import httpcloak

        url = LISTING_TEMPLATE.format(slug=self.company_slug)
        try:
            response = httpcloak.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self.timeout,
            )
        except Exception as exc:
            raise ScraperError(
                f"JazzHR ({self.company_slug}) httpcloak failed: {exc}"
            ) from exc
        if response.status_code == 404:
            raise CompanyNotFoundError(
                f"JazzHR tenant not found: {self.company_slug}"
            )
        if response.status_code != 200:
            raise ScraperError(
                f"JazzHR ({self.company_slug}) httpcloak returned "
                f"{response.status_code}"
            )
        return response.text

    # --- parsing --------------------------------------------------------

    def _parse_listing(self, html_text: str) -> list[Job]:
        jobs: list[Job] = []
        seen: set[str] = set()
        for row_match in _ROW_RE.finditer(html_text):
            body = row_match.group("body")
            title_match = _TITLE_RE.search(body)
            if not title_match:
                continue
            ats_id = title_match.group("id")
            if ats_id in seen:
                continue
            seen.add(ats_id)
            title = _strip_tags(title_match.group("title"))
            if not title:
                continue
            dept_match = _DEPT_RE.search(body)
            department = (
                _strip_tags(dept_match.group("dept")) if dept_match else None
            ) or None
            location = self._extract_location(body)
            jobs.append(
                Job(
                    url=JOB_URL_TEMPLATE.format(slug=self.company_slug, id=ats_id),
                    title=title,
                    company=self.company_slug,
                    ats_type=ATSType.JAZZHR,
                    ats_id=ats_id,
                    location=location,
                    department=department,
                    posted_at=None,
                    fetched_at=datetime.now(),
                )
            )
        return jobs

    def _extract_location(self, row_body: str) -> str | None:
        """The location is the text content of the row's last `<td>`. We
        skip the first <td> (which contains the title link) by stripping
        anchors and department spans, then take the trailing whitespace-
        normalized text."""
        # Drop the title <td> by removing everything up through the first <br>
        # OR <span class="resumator_department">. Whichever last marker we find,
        # the remaining tail is the location <td> body.
        # Simpler: stripped text from each <td> in order; last is location.
        tds = re.findall(r"<td[^>]*>(.*?)</td>", row_body, re.DOTALL | re.IGNORECASE)
        if len(tds) < 2:
            return None
        location = _strip_tags(tds[-1])
        return location or None


class _WAFBlocked(Exception):  # noqa: N818
    """Internal signal: httpx hit a 403; caller decides whether to fall
    back to httpcloak or surface the error."""


def _strip_tags(text: str) -> str:
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()
