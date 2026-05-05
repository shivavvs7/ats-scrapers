"""Tesla careers scraper — placeholder.

⚠️  REQUIRES BROWSER — Tesla's public JSON endpoint
(`https://www.tesla.com/cua-api/apps/careers/state`) is gated by Akamai
bot detection and returns 403 to direct httpx calls. The legacy
`tesla/main.py` uses Playwright to bypass this.

Until 0.2.0 ships an integrated Playwright path (or a scraping proxy),
calling `.fetch()` raises `NotImplementedError`. Use the legacy scraper
in the upstream `tesla/` directory.
"""

from __future__ import annotations

from jobhive.exceptions import ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry


@ScraperRegistry.register(ATSType.TESLA)
class TeslaScraper(BaseScraper):
    """Tesla scraper — requires Playwright. Not yet supported in jobhive."""

    ats = ATSType.TESLA

    def fetch(self) -> list[Job]:
        raise ScraperError(
            "Tesla's careers API is gated by Akamai and requires a real browser. "
            "Use the legacy `tesla/main.py` (Playwright) until jobhive 0.2 adds "
            "an optional browser backend."
        )
