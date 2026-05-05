"""Oracle Taleo Business Edition (TBE) careers scraper.

Taleo Business Edition is the SMB-tier Oracle ATS — its Enterprise Edition
counterpart now lives on ``oraclecloud.com`` and is handled by ``OracleScraper``.

TBE career sites live on a sharded host pattern:

    https://{ph{c}}.tbe.taleo.net/{ph{c}NN}/ats/careers/v2/searchResults
        ?org={ORG}&cws={N}

where ``ph{c}`` (``phe``, ``phf``, ``phh``, ``phq``, etc.) is a regional shard
and ``{ph{c}NN}`` is the per-tenant instance. ``ORG`` is the company code
and ``cws`` is the career-website ID.

Job links look like:

    <h4 class="oracletaleocwsv2-head-title">
      <a href=".../viewRequisition?org=X&cws=N&rid=NNN" class="viewJobLink">
        Title
      </a>
    </h4>

The scraper accepts either a full search-results URL (most reliable) or
the bare components.
"""

from __future__ import annotations

import asyncio
import html
import re
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from jobhive.exceptions import CompanyNotFoundError, ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

if TYPE_CHECKING:
    pass

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.5

# Each job is rendered as `<a class="viewJobLink" href="...rid=NN">Title</a>`.
_JOB_LINK_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]*viewRequisition[^"]*\brid=(?P<rid>\d+)[^"]*)"'
    r'[^>]*class="(?:[^"]*\s)?viewJobLink(?:\s[^"]*)?"[^>]*>'
    r'(?P<title>.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


@ScraperRegistry.register(ATSType.TALEO)
class TaleoScraper(BaseScraper):
    """Taleo TBE scraper. ``company_slug`` is the full search-results URL,
    e.g. ``"https://phe.tbe.taleo.net/phe01/ats/careers/v2/searchResults?org=UH9TY5&cws=41"``.

    A bare ``ORG`` code isn't enough — the regional shard (``phe`` vs ``phh``)
    and instance number (``phe01``) and ``cws`` ID vary per tenant and there's
    no public lookup. Discover the URL once via the company's careers page.
    """

    ats = ATSType.TALEO

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[Job]:
        url = self._validate_url(self.company_slug)
        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            html_text = await self._fetch_with_retry(client, url)
        return self._parse_listing(html_text, base_url=url)

    def _validate_url(self, slug: str) -> str:
        if not slug.startswith(("http://", "https://")):
            raise ScraperError(
                f"Taleo slug must be a full URL "
                f"(https://{{phN}}.tbe.taleo.net/{{phNN}}/ats/careers/v2/searchResults?org=X&cws=N), "
                f"got {slug!r}"
            )
        if "tbe.taleo.net" not in slug:
            raise ScraperError(
                f"Taleo URL must contain `tbe.taleo.net`, got {slug!r}"
            )
        return slug.rstrip("/")

    async def _fetch_with_retry(
        self, client: httpx.AsyncClient, url: str
    ) -> str:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Taleo fetch failed for {url}: {exc}"
                    ) from exc
                await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                continue
            if response.status_code == 404:
                raise CompanyNotFoundError(f"Taleo career site not found: {url}")
            if response.status_code == 200:
                return response.text
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Taleo returned {response.status_code} for {url} "
                        f"after {MAX_RETRIES} retries"
                    )
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after) if retry_after and retry_after.isdigit()
                    else RETRY_BASE_DELAY * (2 ** attempt)
                )
                await asyncio.sleep(delay)
                continue
            raise ScraperError(
                f"Taleo returned {response.status_code} for {url}"
            )
        raise ScraperError(f"Taleo exhausted retries for {url}")

    def _parse_listing(self, html_text: str, *, base_url: str) -> list[Job]:
        company = _company_from_url(base_url)
        seen: set[str] = set()
        jobs: list[Job] = []
        for match in _JOB_LINK_RE.finditer(html_text):
            rid = match.group("rid")
            if rid in seen:
                # Each job typically renders the title link plus a redundant
                # "View" button — both have viewJobLink class. Dedup by rid.
                continue
            seen.add(rid)
            href = html.unescape(match.group("href"))
            title = _strip(match.group("title"))
            if not title:
                continue
            jobs.append(
                Job(
                    url=href,
                    title=title,
                    company=company,
                    ats_type=ATSType.TALEO,
                    ats_id=rid,
                    location=None,  # location requires per-job page fetch
                    posted_at=None,
                    fetched_at=datetime.now(),
                )
            )
        return jobs


def _company_from_url(url: str) -> str:
    """Extract the ``org`` query parameter as the company name. Falls back
    to the host's first label."""
    m = re.search(r"[?&]org=([^&#]+)", url)
    if m:
        return m.group(1)
    host = urlparse(url).hostname or ""
    return host.split(".", 1)[0]


def _strip(text: str) -> str:
    """Strip tags + entities + collapse whitespace."""
    cleaned = _TAG_RE.sub(" ", text)
    cleaned = html.unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
