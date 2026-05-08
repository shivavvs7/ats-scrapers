"""Tesla careers scraper — Browserbase-backed.

Tesla's public listings live behind ``/cua-api/apps/careers/state``,
which returns the entire job catalog as one JSON document. Direct
``httpx`` calls are 403'd by Akamai bot detection — a real browser is
required, with cookies + JS challenges from a prior visit to
``tesla.com``.

We use Browserbase as the remote browser host so the public library
doesn't ship its own Chrome binary. Set ``JOBHIVE_USE_BROWSERBASE=1``
together with ``BROWSERBASE_API_KEY`` / ``BROWSERBASE_PROJECT_ID`` to
enable. Without the flag, this scraper logs a warning and returns
``[]`` so a full-pipeline run keeps moving.

Caveat — Akamai's IP and TLS fingerprinting on ``tesla.com`` is
aggressive: as of 2026-05, default Browserbase sessions (with or
without their built-in residential proxies) still get an "Access
Denied" challenge page. Until the Browserbase project is configured
with a proxy / fingerprint that Tesla accepts, this scraper will
raise ``ScraperError`` on the JSON parse. The code path itself is
correct; only the network frontend needs work.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from typing import Any

from jobhive.exceptions import ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers import _browserbase as bb
from jobhive.scrapers.base import BaseScraper, ScraperRegistry

_BASE_URL = "https://www.tesla.com"
_CAREERS_HOME = "/careers/search/jobs"
_STATE_ENDPOINT = "/cua-api/apps/careers/state"

# Match the JSON body whether the browser wraps it in <pre>…</pre> or
# inlines it as plain text. Both forms appear in the wild depending on
# user-agent / accept headers.
_PRE_RE = re.compile(r"<pre[^>]*>(.*?)</pre>", re.DOTALL)


@ScraperRegistry.register(ATSType.TESLA)
class TeslaScraper(BaseScraper):
    """Tesla scraper. Single tenant — slug is ignored."""

    ats = ATSType.TESLA

    def fetch(self) -> list[Job]:
        if not bb.is_enabled():
            bb.warn_disabled("Tesla")
            return []
        bb.require_playwright()
        api_key, project_id = bb.require_creds()
        return asyncio.run(self._fetch_via_browserbase(api_key, project_id))

    async def _fetch_via_browserbase(
        self, api_key: str, project_id: str
    ) -> list[Job]:
        from playwright.async_api import async_playwright

        ws_url = await bb.create_session_ws_url(api_key, project_id)
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws_url)
            try:
                ctx = browser.contexts[0]
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()

                # Warm up Akamai cookies by visiting the careers page first.
                await page.goto(
                    f"{_BASE_URL}{_CAREERS_HOME}",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )

                # Now hit the JSON endpoint — same browser context, same
                # cookies, no bot-block.
                await page.goto(
                    f"{_BASE_URL}{_STATE_ENDPOINT}",
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
                payload = await self._extract_json(page)
            finally:
                await browser.close()

        return list(self._parse_payload(payload))

    @staticmethod
    async def _extract_json(page: Any) -> dict[str, Any]:
        html = await page.content()
        match = _PRE_RE.search(html)
        body = match.group(1) if match else await page.inner_text("body")
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ScraperError(
                f"Tesla: response did not parse as JSON ({exc}). "
                "Akamai may have served a challenge page."
            ) from exc

    def _parse_payload(self, payload: dict[str, Any]) -> list[Job]:
        listings = payload.get("listings") or []
        locations = (payload.get("lookup") or {}).get("locations") or {}
        departments = (payload.get("lookup") or {}).get("departments") or {}
        fetched_at = datetime.now(tz=UTC)
        jobs: list[Job] = []
        for entry in listings:
            job_id = entry.get("id") or entry.get("ji")
            title = entry.get("t") or entry.get("title")
            if not job_id or not title:
                continue
            location = locations.get(entry.get("l"))
            department_id = entry.get("d")
            department = departments.get(department_id) if department_id else None
            slug = self._url_slug(title, str(job_id))
            url = f"{_BASE_URL}/careers/search/job/{slug}"
            jobs.append(
                Job(
                    url=url,
                    title=title,
                    company="Tesla",
                    ats_type=ATSType.TESLA,
                    ats_id=str(job_id),
                    location=location,
                    department=department,
                    fetched_at=fetched_at,
                    raw=entry,
                )
            )
        return jobs

    @staticmethod
    def _url_slug(title: str, job_id: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        return f"{slug}-{job_id}" if slug else job_id
