"""Meta careers scraper — placeholder.

⚠️  REQUIRES BROWSER — metacareers.com is rendered client-side and the
GraphQL endpoint that backs the listing requires session tokens that are
only obtainable from a real browser context. The legacy `meta/main.py`
uses Playwright to intercept the GraphQL responses.

Until 0.2.0 ships an integrated browser backend, calling `.fetch()` raises.
"""

from __future__ import annotations

from jobhive.exceptions import ScraperError
from jobhive.models import ATSType, Job
from jobhive.scrapers.base import BaseScraper, ScraperRegistry


@ScraperRegistry.register(ATSType.META)
class MetaScraper(BaseScraper):
    """Meta scraper — requires Playwright. Not yet supported in jobhive."""

    ats = ATSType.META

    def fetch(self) -> list[Job]:
        raise ScraperError(
            "Meta's careers site is client-side rendered and the backing GraphQL "
            "API requires browser-issued tokens. Use the legacy `meta/main.py` "
            "(Playwright) until jobhive 0.2 adds an optional browser backend."
        )
