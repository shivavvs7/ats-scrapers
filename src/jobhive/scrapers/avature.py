"""Avature scraper.

Avature powers career sites for many enterprises (Bloomberg, IBM, Astellas,
etc.). There is no public JSON API — every tenant serves a server-rendered
search page at:

    GET https://{slug}.avature.net/careers/SearchJobs/
        ?jobOffset={N}&jobRecordsPerPage=12

Some tenants (notably IBM) host on a custom domain like
``careers.ibm.com/en_US/careers/SearchJobs/`` — for those, pass the full
base URL as ``company_slug`` and the path/locale prefix is preserved.

The HTML markup varies between tenants — Bloomberg uses ``article.job``,
IBM uses ``div.job-item``, Astellas uses table rows. We try a chain of
known selectors with a final fallback to plain ``<a href=".../JobDetail/...">``
anchors.

Avature is selective about clients — they reject bare ``Mozilla/5.0`` UAs
on some tenants. We send full browser headers (Chrome 143 on macOS) plus
``Sec-Fetch-*`` to mimic a real navigation.
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
    pass

PAGE_SIZE = 12  # Avature's default page size.
MAX_PAGES = 200  # Defensive upper bound — caps a runaway loop at ~2400 jobs.
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.5

# Locale path prefixes that some tenants insert (`careers.ibm.com/en_US/...`).
_LOCALE_PREFIXES = {
    "en_US", "en_GB", "en_CA", "en_AU", "en_IN", "en_SG",
    "fr_FR", "fr_CA", "es_ES", "es_MX", "de_DE", "it_IT",
    "pt_BR", "pt_PT", "zh_CN", "zh_TW", "ja_JP", "ko_KR", "nl_NL",
}

# Pseudo-anchor texts that aren't real jobs (action buttons rendered as <a>).
_PSEUDO_TITLES = {
    "apply", "apply now", "apply online", "learn more", "view job",
    "view all", "see job", "more info", "details",
}

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/143.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}


@ScraperRegistry.register(ATSType.AVATURE)
class AvatureScraper(BaseScraper):
    """Avature scraper. ``company_slug`` is either a bare slug
    (``"bloomberg"`` → ``https://bloomberg.avature.net``) or a full base URL
    for tenants on custom domains (``"https://careers.ibm.com/en_US"``)."""

    ats = ATSType.AVATURE

    def fetch(self) -> list[Job]:
        return asyncio.run(self._fetch_async())

    async def _fetch_async(self) -> list[Job]:
        base = self._resolve_base_url()
        company = _company_from_base(base) or self.company_slug
        seen: set[str] = set()
        all_jobs: list[Job] = []

        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            for page_num in range(MAX_PAGES):
                offset = page_num * PAGE_SIZE
                html_text = await self._fetch_page(client, base, offset)
                page_jobs = self._parse_page(html_text, base, company)
                new = [j for j in page_jobs if j.ats_id not in seen]
                if not new:
                    break
                for j in new:
                    seen.add(j.ats_id)
                all_jobs.extend(new)
                # Termination: short page = last page.
                if len(page_jobs) < PAGE_SIZE:
                    break
        return all_jobs

    async def _fetch_page(
        self, client: httpx.AsyncClient, base: str, offset: int
    ) -> str:
        url = f"{base}/careers/SearchJobs/"
        params = {"jobOffset": offset, "jobRecordsPerPage": PAGE_SIZE}
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = await client.get(
                    url, params=params, headers=_BROWSER_HEADERS
                )
            except httpx.HTTPError as exc:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Avature fetch failed for {base} at offset={offset}: {exc}"
                    ) from exc
                await asyncio.sleep(RETRY_BASE_DELAY * attempt)
                continue
            if response.status_code == 404:
                raise CompanyNotFoundError(f"Avature site not found: {base}")
            if response.status_code == 200:
                return response.text
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt == MAX_RETRIES:
                    raise ScraperError(
                        f"Avature ({base}) returned {response.status_code} at "
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
                f"Avature ({base}) returned {response.status_code} at offset={offset}"
            )
        raise ScraperError(f"Avature ({base}) exhausted retries at offset={offset}")

    def _resolve_base_url(self) -> str:
        slug = self.company_slug
        if slug.startswith(("http://", "https://")):
            return slug.rstrip("/")
        return f"https://{slug}.avature.net"

    def _parse_page(self, html_text: str, base: str, company: str) -> list[Job]:
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:  # pragma: no cover
            raise ScraperError(
                "Avature scraper requires beautifulsoup4. Install with "
                "`pip install jobhive[scrapers]` or `pip install beautifulsoup4`."
            ) from exc

        soup = BeautifulSoup(html_text, "html.parser")
        # Strategy: find all `/JobDetail/` anchors (the canonical job URL
        # form), then for each walk up to the nearest wrapping container
        # (article / div / li / tr). The wrapper is where title/location/
        # department live as sibling elements. This handles all tenant
        # markups (Bloomberg `article--result`, IBM `div.job-item`, etc.)
        # without maintaining a per-tenant selector list.
        anchors = soup.find_all(
            "a", href=lambda h: bool(h) and "/JobDetail/" in h
        )
        seen_ids: set[str] = set()
        jobs: list[Job] = []
        for anchor in anchors:
            # Walk up to the first sensible container.
            container = anchor.find_parent(["article", "li", "tr"]) or anchor.find_parent(
                "div",
                class_=lambda v: bool(v) and any(
                    k in str(v).lower() for k in ("job", "result", "listing", "article")
                ),
            )
            element = container or anchor
            job = _parse_job_element(element, anchor, base, company)
            if job is None or job.ats_id in seen_ids:
                continue
            seen_ids.add(job.ats_id)
            jobs.append(job)
        return jobs


def _parse_job_element(
    element: object, anchor: object, base: str, company: str
) -> Job | None:
    href = (anchor.get("href") or "").strip()  # type: ignore[union-attr]
    if not href or "/JobDetail/" not in href:
        return None

    # Build absolute URL.
    if href.startswith(("http://", "https://")):
        url = href
    else:
        url = f"{base}{href if href.startswith('/') else '/' + href}"

    # Job ID = last non-empty path segment (strip query string).
    ats_id = href.rsplit("?", 1)[0].rstrip("/").rsplit("/", 1)[-1]
    if not ats_id:
        return None

    # Title preference order:
    # 1. A heading inside the wrapper (`<h2>` / `<h3>`).
    # 2. An element with a *title* class.
    # 3. The anchor text itself — fine when the anchor IS the title link
    #    (Bloomberg, IBM), useless when it's an "Apply" button (skip those).
    title = ""
    title_el = (
        element.find(["h2", "h3"])  # type: ignore[union-attr]
        or element.find(  # type: ignore[union-attr]
            class_=lambda v: bool(v) and "title" in str(v).lower()
        )
    )
    if title_el is not None:
        title = title_el.get_text(strip=True)
    if not title:
        anchor_text = anchor.get_text(strip=True)  # type: ignore[union-attr]
        if anchor_text.lower() in _PSEUDO_TITLES:
            return None
        title = anchor_text
    title = re.sub(r"\s+", " ", title).strip()
    if not title or title.lower() in _PSEUDO_TITLES:
        return None

    # Location: any element with a "location" class.
    location: str | None = None
    loc_el = element.find(  # type: ignore[union-attr]
        class_=lambda v: bool(v) and "location" in str(v).lower()
    )
    if loc_el is not None:
        location = re.sub(r"\s+", " ", loc_el.get_text(strip=True)).strip() or None

    # Department: class contains "department" or "category".
    department: str | None = None
    dept_el = element.find(  # type: ignore[union-attr]
        class_=lambda v: bool(v) and any(
            k in str(v).lower() for k in ("department", "category")
        )
    )
    if dept_el is not None:
        department = (
            re.sub(r"\s+", " ", dept_el.get_text(strip=True)).strip() or None
        )

    return Job(
        url=url,
        title=title,
        company=company,
        ats_type=ATSType.AVATURE,
        ats_id=ats_id,
        location=location,
        department=department,
        posted_at=None,
        fetched_at=datetime.now(),
    )


def _company_from_base(base: str) -> str | None:
    """Best-effort company name from an Avature URL.

    ``bloomberg.avature.net`` → ``"Bloomberg"``
    ``careers.ibm.com``       → ``"Ibm"``
    """
    host = (urlparse(base).netloc or "").lower()
    parts = [p for p in host.split(".") if p]
    if not parts:
        return None
    name = parts[0]
    if name in {"careers", "jobs"} and len(parts) > 1:
        name = parts[1]
    return name.replace("-", " ").title()


def _ensure_locale_in_base(base: str) -> str:
    """If the URL's first path segment is a locale, keep it; else strip path."""
    parsed = urlparse(base)
    path_parts = [p for p in parsed.path.split("/") if p]
    if path_parts and path_parts[0] in _LOCALE_PREFIXES:
        return f"{parsed.scheme}://{parsed.netloc}/{path_parts[0]}"
    return f"{parsed.scheme}://{parsed.netloc}"
