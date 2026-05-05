"""Tests for the iCIMS scraper.

iCIMS career sites are HTML — each tenant lives at
``careers-{slug}.icims.com``. The actual listings are inside an iframe;
we hit ``/jobs/search?in_iframe=1`` directly.
"""

from __future__ import annotations

import pytest

from jobhive.exceptions import CompanyNotFoundError, ScraperError
from jobhive.models import ATSType
from jobhive.scrapers import ScraperRegistry, iCIMSScraper


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    import jobhive.scrapers.icims as ic
    monkeypatch.setattr(ic, "MAX_RETRIES", 1)
    monkeypatch.setattr(ic, "RETRY_BASE_DELAY", 0.0)


def _page_url(slug: str, page: int) -> str:
    return f"https://careers-{slug}.icims.com/jobs/search?ss=1&pr={page}&in_iframe=1"


def _job_anchor(job_id: str, title: str, slug: str = "acme") -> str:
    return (
        f'<a href="https://careers-{slug}.icims.com/jobs/{job_id}/{title.lower().replace(" ", "-")}/job?in_iframe=1" '
        f'class="iCIMS_Anchor">'
        f'<h3>{title}</h3>'
        f'</a>'
    )


def _page(anchors: list[str]) -> str:
    return f"<html><body>{''.join(anchors)}</body></html>"


# --- Registry ---------------------------------------------------------------


def test_registry_resolves_icims() -> None:
    assert ScraperRegistry.get(ATSType.ICIMS) is iCIMSScraper


# --- Construction -----------------------------------------------------------


def test_default_base_url_built_from_slug() -> None:
    s = iCIMSScraper("acme")
    assert s.base_url == "https://careers-acme.icims.com"


def test_full_url_accepted() -> None:
    s = iCIMSScraper("https://uscareers-rws.icims.com")
    assert s.base_url == "https://uscareers-rws.icims.com"


def test_company_name_derived_from_subdomain() -> None:
    """``careers-peraton.icims.com`` → ``peraton``."""
    s = iCIMSScraper("peraton")
    assert s._company_name() == "peraton"


def test_uscareers_prefix_stripped() -> None:
    s = iCIMSScraper("https://uscareers-rws.icims.com")
    assert s._company_name() == "rws"


# --- Page parsing -----------------------------------------------------------


def test_parses_basic_listing(httpx_mock) -> None:
    httpx_mock.add_response(
        url=_page_url("acme", 0),
        text=_page([
            _job_anchor("100", "Senior Engineer"),
            _job_anchor("101", "Designer"),
        ]),
    )
    httpx_mock.add_response(url=_page_url("acme", 1), text=_page([]))
    jobs = iCIMSScraper("acme").fetch()
    assert len(jobs) == 2
    assert jobs[0].ats_id == "100"
    assert jobs[0].title == "Senior Engineer"
    assert jobs[0].company == "acme"
    assert jobs[0].ats_type is ATSType.ICIMS
    assert str(jobs[0].url).startswith("https://careers-acme.icims.com/jobs/100")


def test_returns_empty_for_listing_with_no_jobs(httpx_mock) -> None:
    httpx_mock.add_response(url=_page_url("acme", 0), text=_page([]))
    assert iCIMSScraper("acme").fetch() == []


def test_dedupes_jobs_with_same_id(httpx_mock) -> None:
    httpx_mock.add_response(
        url=_page_url("acme", 0),
        text=_page([
            _job_anchor("100", "Engineer"),
            _job_anchor("100", "Engineer dup"),
        ]),
    )
    httpx_mock.add_response(url=_page_url("acme", 1), text=_page([]))
    jobs = iCIMSScraper("acme").fetch()
    assert len(jobs) == 1


def test_skips_anchor_without_h3_title(httpx_mock) -> None:
    """Some anchors are non-job (e.g. the "Apply" button has no h3)."""
    page = _page([
        '<a href="https://careers-acme.icims.com/jobs/999/apply/job?in_iframe=1" class="iCIMS_Anchor">Apply</a>',
        _job_anchor("100", "Real Job"),
    ])
    httpx_mock.add_response(url=_page_url("acme", 0), text=page)
    httpx_mock.add_response(url=_page_url("acme", 1), text=_page([]))
    jobs = iCIMSScraper("acme").fetch()
    assert [j.ats_id for j in jobs] == ["100"]


def test_decodes_html_entities_in_url(httpx_mock) -> None:
    """iCIMS encodes special characters in slugs (`%26` for ``&``).
    The href in the rendered Job model should keep the entity decoded."""
    page = (
        '<a href="https://careers-acme.icims.com/jobs/100/r%26d-engineer/job?in_iframe=1" '
        'class="iCIMS_Anchor"><h3>R&amp;D Engineer</h3></a>'
    )
    httpx_mock.add_response(url=_page_url("acme", 0), text=page)
    httpx_mock.add_response(url=_page_url("acme", 1), text=_page([]))
    jobs = iCIMSScraper("acme").fetch()
    assert jobs[0].title == "R&D Engineer"


# --- Pagination -------------------------------------------------------------


def test_paginates_until_no_new_ids(httpx_mock) -> None:
    httpx_mock.add_response(
        url=_page_url("acme", 0),
        text=_page([_job_anchor(str(i), f"Job {i}") for i in range(25)]),
    )
    httpx_mock.add_response(
        url=_page_url("acme", 1),
        text=_page([_job_anchor(str(i), f"Job {i}") for i in range(25, 40)]),
    )
    # Page 2 returns same as page 1 — no new IDs → terminate.
    httpx_mock.add_response(
        url=_page_url("acme", 2),
        text=_page([_job_anchor(str(i), f"Job {i}") for i in range(25)]),
    )
    jobs = iCIMSScraper("acme").fetch()
    assert len(jobs) == 40


def test_terminates_immediately_on_empty_first_page(httpx_mock) -> None:
    httpx_mock.add_response(url=_page_url("acme", 0), text=_page([]))
    assert iCIMSScraper("acme").fetch() == []


# --- Error handling ---------------------------------------------------------


def test_raises_company_not_found_on_404(httpx_mock) -> None:
    httpx_mock.add_response(url=_page_url("missing", 0), status_code=404)
    with pytest.raises(CompanyNotFoundError):
        iCIMSScraper("missing").fetch()


def test_5xx_retries(monkeypatch, httpx_mock) -> None:
    import jobhive.scrapers.icims as ic
    monkeypatch.setattr(ic, "MAX_RETRIES", 3)
    httpx_mock.add_response(url=_page_url("acme", 0), status_code=503)
    httpx_mock.add_response(
        url=_page_url("acme", 0),
        text=_page([_job_anchor("1", "X")]),
    )
    httpx_mock.add_response(url=_page_url("acme", 1), text=_page([]))
    jobs = iCIMSScraper("acme").fetch()
    assert len(jobs) == 1


def test_5xx_exhausts_retries(monkeypatch, httpx_mock) -> None:
    import jobhive.scrapers.icims as ic
    monkeypatch.setattr(ic, "MAX_RETRIES", 3)
    httpx_mock.add_response(url=_page_url("acme", 0), status_code=502, is_reusable=True)
    with pytest.raises(ScraperError, match="502"):
        iCIMSScraper("acme").fetch()
