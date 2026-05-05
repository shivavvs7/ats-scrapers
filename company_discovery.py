#!/usr/bin/env python3
"""Unified ATS company discovery for jobhive.

Replaces the older `firecrawl_discovery.py`, `searxng_discovery.py`, and
`serpapi_discovery.py` with a single CLI tool. One config dict + one pipeline.

Pipeline (each step optional, controllable via --backend):

    1. Firecrawl /map on the ATS marketing sites — surfaces customer logos
       and case studies that link to real tenants. Cheap and high-yield.
    2. SerpAPI Google searches with `site:` queries — long-tail tenants.
    3. Firecrawl /search with industry × country × keyword queries — covers
       what /map and SerpAPI miss.
    4. SearXNG (if `SEARXNG_URL` is reachable) — free unlimited fallback.
    5. Validation — hits each candidate against the ATS-specific URL and
       checks the response shape. Uses httpx or httpcloak per platform.

Usage:

    python company_discovery.py recruitee
    python company_discovery.py bamboohr --backend map,serp
    python company_discovery.py --all --max-queries 50
    python company_discovery.py jazzhr --httpcloak
    python company_discovery.py teamtailor --no-validate

Output: appends new tenants to `<ats>/<ats>_companies.csv` (never overwrites
existing entries).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import re
import sys
from datetime import datetime
from itertools import product
from pathlib import Path
from typing import Any, Callable

import httpx

REPO = Path(__file__).resolve().parent


# ---------------------------------------------------------------- platforms --

# Each platform config:
#   patterns:        list of regexes (named group `slug`) for extracting tenant
#                    identifiers from URLs found in maps/searches
#   marketing:       list of marketing/blog/help domains to /map (cheap big yield)
#   search_domain:   token for `site:X` queries
#   validate_url:    template with `{slug}` — the per-tenant URL to probe
#   validate:        function (response) -> tuple[name, ats_id_count] | None
#   client:          'httpx' (default) or 'httpcloak' (for CF-protected sites)
#   output_file:     CSV path relative to REPO
#   skip_slugs:      reserved slugs that aren't real tenants (www, api, blog…)


def _validate_recruitee(r: httpx.Response) -> tuple[str, int] | None:
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    offers = data.get("offers")
    if not isinstance(offers, list):
        return None
    name = next(
        (o.get("company_name") for o in offers if isinstance(o, dict) and o.get("company_name")),
        None,
    )
    return (name or "", len(offers))


def _validate_lever(r: httpx.Response) -> tuple[str, int] | None:
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    return ("", len(data))


def _validate_greenhouse(r: httpx.Response) -> tuple[str, int] | None:
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return None
    return ("", len(jobs))


def _validate_ashby(r: httpx.Response) -> tuple[str, int] | None:
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return None
    return ("", len(jobs))


def _validate_workable(r: httpx.Response) -> tuple[str, int] | None:
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return None
    name = data.get("name") if isinstance(data, dict) else None
    return (name or "", len(jobs))


def _validate_smartrecruiters(r: httpx.Response) -> tuple[str, int] | None:
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, list):
        return None
    return ("", data.get("totalFound") or len(content))


def _validate_bamboohr(r: httpx.Response) -> tuple[str, int] | None:
    """BambooHR returns 200 for ALL subdomains via wildcard catch-all.
    Real tenants serve a different page; the catch-all is exactly 47903 bytes
    and titled 'BambooHR: The Complete HR Software'.
    """
    if r.status_code != 200:
        return None
    text = r.text or ""
    if len(text) == 47903 or "The Complete HR Software" in text[:500]:
        return None
    return ("", 0)


def _validate_teamtailor(r: httpx.Response) -> tuple[str, int] | None:
    if r.status_code != 200:
        return None
    text = r.text or ""
    if "404 the page you are looking for could not be found" in text.lower():
        return None
    return ("", 0)


def _validate_jazzhr(r: httpx.Response) -> tuple[str, int] | None:
    if r.status_code != 200:
        return None
    text = r.text or ""
    if len(text) < 1000:
        return None
    lower = text.lower()
    # JazzHR redirects unknown subdomains to www.jazzhr.com (marketing
    # site) and expired tenants serve an "Inactive Career Page"
    # template. Both responses look superficially valid (200 + long
    # HTML); we have to read the markers explicitly.
    if "inactive career page" in lower:
        return None
    if "this page does not exist" in lower:
        return None
    # JazzHR redirects unknown/dead subdomains to ``www.jazzhr.com``
    # (marketing). Pages on the marketing site have a distinctive title
    # and CTAs that real tenant career pages never carry.
    marketing_markers = (
        "recruiting software for small business",
        "applicant tracking system for small",
        "request a demo",
        "schedule a demo",
        "free 21-day trial",
    )
    marketing_hits = sum(1 for m in marketing_markers if m in lower)
    # Real tenant pages have job-listing markers.
    tenant_markers = (
        "joblisting", "job listing", "job_listing",
        "apply for this job", "jobtitlewrap", "job-search",
        "» job listing",
    )
    tenant_hits = sum(1 for m in tenant_markers if m in lower)
    if marketing_hits >= 1 and tenant_hits == 0:
        # Marketing redirect — almost certainly a dead/unknown tenant.
        return None
    if tenant_hits == 0:
        return None
    return ("", tenant_hits)


def _validate_rippling(r: httpx.Response) -> tuple[str, int] | None:
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    items = (data.get("items") or data.get("jobs") if isinstance(data, dict) else None)
    if isinstance(data, list):
        items = data
    if not isinstance(items, list):
        return None
    return ("", len(items))


def _validate_breezy(r: httpx.Response) -> tuple[str, int] | None:
    """BreezyHR returns 200 with a JSON array of positions for active sites,
    302 redirect to breezy.hr/ for slugs without a careers page."""
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if not isinstance(data, list):
        return None
    return ("", len(data))


def _validate_cornerstone(r: httpx.Response) -> tuple[str, int] | None:
    """Cornerstone career sites embed a JWT in the HTML — its presence is
    the strongest signal that a tenant exists. We don't probe the API
    here (would need region detection); just check the marker."""
    if r.status_code != 200:
        return None
    text = r.text or ""
    if "csod.context.token" not in text and "csod_user_token" not in text:
        return None
    # We can't get an accurate job count without a follow-up API call —
    # return a sentinel 1 so the discovery script counts the tenant.
    return ("", 1)


def _validate_icims(r: httpx.Response) -> tuple[str, int] | None:
    """iCIMS career sites embed an iframe with the actual listings. The
    careers-* host returning 200 with `iCIMS_Anchor` markup is sufficient."""
    if r.status_code != 200:
        return None
    text = r.text or ""
    if "iCIMS" not in text:
        return None
    return ("", 1)


def _validate_successfactors(r: httpx.Response) -> tuple[str, int] | None:
    """SuccessFactors recruiting-marketing sites expose `sitemal.xml`. The
    presence of an RSS root with `<channel>` plus at least one `<item>`
    confirms the tenant has a feed."""
    if r.status_code != 200:
        return None
    text = r.text or ""
    if "<rss" not in text or "<channel>" not in text:
        return None
    n_items = text.count("<item>")
    return ("", n_items)


def _validate_taleo(r: httpx.Response) -> tuple[str, int] | None:
    """Taleo TBE search-results page exposes `viewJobLink` anchors per job."""
    if r.status_code != 200:
        return None
    text = r.text or ""
    n = text.count("viewJobLink")
    if n == 0 and "oracletaleocwsv2" not in text:
        return None
    # Each job typically has 2 viewJobLink anchors (title + view button).
    return ("", max(n // 2, 1))


def _validate_workday(r: httpx.Response) -> tuple[str, int] | None:
    """Hit ``GET https://{slug}/jobs`` (the public careers list).

    Workday content-negotiates aggressively. With ``Accept: application/json``
    in the first slot it returns a tiny JSON widget directive
    (``{"widget":"redirect","url":"/{board}/jobs","externalSpa":true}``),
    which is the cleanest "real tenant" signal. With HTML-first Accept
    we get the full SPA shell that carries fingerprints like ``wday/``,
    ``data-automation-id``, ``myworkdayjobs``. Either form is enough.
    Empty/4xx/5xx → unknown or dead.
    """
    if r.status_code != 200:
        return None
    text = (r.text or "").strip()
    if not text:
        return None
    lower = text.lower()
    # JSON widget shape — short, very specific.
    if text.startswith("{") and ('"widget"' in lower or '"externalspa"' in lower):
        return ("", 0)
    # HTML SPA shell.
    if any(m in lower for m in (
        "wday/", "myworkdayjobs", "data-automation-id",
        "careersfacets", "jobsearch", "phsubmenu", "wd-pop",
    )):
        return ("", 0)
    return None


def _validate_eightfold(r: httpx.Response) -> tuple[str, int] | None:
    """Eightfold tenants respond on `/api/pcsx/search` with
    `{"data": {"positions": [...], "count": N}}`. We accept presence of
    `positions` (even if empty) as a real-tenant signal because some
    tenants currently have 0 open jobs.
    """
    if r.status_code != 200:
        return None
    try:
        data = r.json().get("data") or {}
    except ValueError:
        return None
    positions = data.get("positions")
    if not isinstance(positions, list):
        return None
    return ("", int(data.get("count") or len(positions)))


def _validate_pinpoint(r: httpx.Response) -> tuple[str, int] | None:
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    return ("", len(items))


def _validate_recruiterbox(r: httpx.Response) -> tuple[str, int] | None:
    # 200 with `meta.total` => valid Recruiterbox tenant. 400 with
    # "Invalid client name" => unknown slug.
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    meta = data.get("meta")
    total = meta.get("total") if isinstance(meta, dict) else None
    if not isinstance(total, int):
        return None
    return ("", total)


def _validate_personio(r: httpx.Response) -> tuple[str, int] | None:
    if r.status_code != 200:
        return None
    try:
        data = r.json()
    except ValueError:
        return None
    if isinstance(data, list):
        return ("", len(data))
    if isinstance(data, dict):
        items = data.get("data") or data.get("jobs") or []
        if isinstance(items, list):
            return ("", len(items))
    return None


PLATFORMS: dict[str, dict[str, Any]] = {
    "recruitee": {
        "patterns": [r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.recruitee\.com"],
        "marketing": ["https://recruitee.com", "https://tellent.com", "https://jobs.recruitee.com"],
        "search_domain": "recruitee.com",
        "validate_url": "https://{slug}.recruitee.com/api/offers",
        "validate": _validate_recruitee,
        "output_file": "recruitee/recruitee_companies.csv",
        "skip_slugs": {"www", "api", "support", "help", "tellent", "blog", "status",
                       "developers", "partners", "jobs", "recruitee", "recruitee3", "demo"},
    },
    "bamboohr": {
        "patterns": [r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.bamboohr\.com"],
        "marketing": ["https://www.bamboohr.com"],
        "search_domain": "bamboohr.com",
        "validate_url": "https://{slug}.bamboohr.com/careers",
        "validate": _validate_bamboohr,
        "output_file": "bamboohr/bamboohr_companies.csv",
        "skip_slugs": {"www", "documentation", "help", "support", "blog", "status",
                       "marketplace", "developer", "developers", "info", "go"},
    },
    "teamtailor": {
        "patterns": [r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.teamtailor\.com"],
        "marketing": ["https://www.teamtailor.com", "https://career.teamtailor.com"],
        "search_domain": "teamtailor.com",
        "validate_url": "https://{slug}.teamtailor.com/",
        "validate": _validate_teamtailor,
        "output_file": "teamtailor/teamtailor_companies.csv",
        "skip_slugs": {"www", "support", "blog", "tt", "career", "careers", "help",
                       "developer", "developers", "partner", "partners"},
    },
    "jazzhr": {
        "patterns": [r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.applytojob\.com"],
        "marketing": ["https://www.jazzhr.com", "https://applytojob.com"],
        "search_domain": "applytojob.com",
        "validate_url": "https://{slug}.applytojob.com/apply/jobs",
        "validate": _validate_jazzhr,
        "client": "httpcloak",  # JazzHR family is Cloudflare-protected
        "output_file": "jazzhr/jazzhr_companies.csv",
        "skip_slugs": {"www", "app", "info", "help", "support", "marketplace", "blog"},
    },
    "lever": {
        "patterns": [r"https?://jobs\.lever\.co/(?P<slug>[a-z0-9][a-z0-9._-]{0,62})"],
        "marketing": [],
        "search_domain": "jobs.lever.co",
        "validate_url": "https://api.lever.co/v0/postings/{slug}?mode=json",
        "validate": _validate_lever,
        "output_file": "lever/lever_companies.csv",
        "skip_slugs": set(),
    },
    "greenhouse": {
        "patterns": [
            r"https?://(?:job-boards|boards)\.greenhouse\.io/(?P<slug>[a-z0-9][a-z0-9-]{0,62})",
        ],
        "marketing": [],
        "search_domain": "greenhouse.io",
        "validate_url": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
        "validate": _validate_greenhouse,
        "output_file": "greenhouse/greenhouse_companies.csv",
        "skip_slugs": set(),
    },
    "ashby": {
        "patterns": [r"https?://jobs\.ashbyhq\.com/(?P<slug>[a-z0-9][a-z0-9-]{0,62})"],
        "marketing": [],
        "search_domain": "jobs.ashbyhq.com",
        "validate_url": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
        "validate": _validate_ashby,
        "output_file": "ashby/ashby_companies.csv",
        "skip_slugs": set(),
    },
    "workable": {
        "patterns": [r"https?://apply\.workable\.com/(?P<slug>[a-z0-9][a-z0-9-]{0,62})"],
        "marketing": [],
        "search_domain": "apply.workable.com",
        "validate_url": "https://apply.workable.com/api/v1/widget/accounts/{slug}",
        "validate": _validate_workable,
        "output_file": "workable/workable_companies.csv",
        "skip_slugs": set(),
    },
    "smartrecruiters": {
        "patterns": [r"https?://jobs\.smartrecruiters\.com/(?P<slug>[A-Za-z0-9][A-Za-z0-9-]{0,62})"],
        "marketing": [],
        "search_domain": "jobs.smartrecruiters.com",
        "validate_url": "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1",
        "validate": _validate_smartrecruiters,
        "output_file": "smartrecruiters/smartrecruiters_companies.csv",
        "skip_slugs": set(),
    },
    "rippling": {
        "patterns": [r"https?://ats\.rippling\.com/(?P<slug>[a-z0-9][a-z0-9-]{0,62})"],
        "marketing": [],
        "search_domain": "ats.rippling.com",
        "validate_url": "https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs",
        "validate": _validate_rippling,
        "output_file": "rippling/rippling_companies.csv",
        "skip_slugs": set(),
    },
    "personio": {
        "patterns": [r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.jobs\.personio\.com"],
        "marketing": ["https://www.personio.com"],
        "search_domain": "jobs.personio.com",
        "validate_url": "https://{slug}.jobs.personio.com/search.json",
        "validate": _validate_personio,
        "output_file": "personio/personio_companies.csv",
        "skip_slugs": {"www", "api", "support", "help"},
    },
    "breezy": {
        # Most Breezy tenants live on `{slug}.breezy.hr`.
        "patterns": [r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.breezy\.hr"],
        "marketing": ["https://breezy.hr", "https://www.breezy.hr"],
        "search_domain": "breezy.hr",
        "validate_url": "https://{slug}.breezy.hr/json",
        "validate": _validate_breezy,
        "output_file": "breezy/breezy_companies.csv",
        "skip_slugs": {"www", "app", "api", "docs", "blog", "support", "help",
                       "developer", "developers", "marketing"},
    },
    "cornerstone": {
        # Cornerstone tenants live on `{slug}.csod.com/ux/ats/careersite/...`.
        "patterns": [r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.csod\.com"],
        "marketing": [
            "https://www.cornerstoneondemand.com",
            "https://www.csod.com",
        ],
        "search_domain": "csod.com",
        "validate_url": "https://{slug}.csod.com/ux/ats/careersite/1/home?c={slug}",
        "validate": _validate_cornerstone,
        "output_file": "cornerstone/cornerstone_companies.csv",
        "skip_slugs": {"www", "app", "developer", "developers", "support", "help",
                       "blog", "products", "learn"},
    },
    "icims": {
        # iCIMS tenants live on `careers-{slug}.icims.com` (rarely
        # `uscareers-{slug}` — a custom-domain alias we don't auto-discover).
        "patterns": [r"https?://careers-(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.icims\.com"],
        "marketing": ["https://www.icims.com"],
        "search_domain": "icims.com",
        "validate_url": "https://careers-{slug}.icims.com/jobs/search?ss=1&in_iframe=1",
        "validate": _validate_icims,
        "output_file": "icims/icims_companies.csv",
        "skip_slugs": {"www", "support", "help", "blog", "developer"},
    },
    "successfactors": {
        # SuccessFactors recruiting-marketing tenants front their own
        # branded host — `job.{company}.com` is the most common form.
        # The slug is the FULL host so the URL composition is straightforward.
        "patterns": [r"https?://(?P<slug>job\.[a-z0-9][a-z0-9.-]+\.[a-z]{2,})/sitemal\.xml"],
        "marketing": ["https://www.successfactors.com", "https://www.sap.com/products/hcm.html"],
        "search_domain": "sitemal.xml",  # SerpAPI: site search for the typo'd path
        "validate_url": "https://{slug}/sitemal.xml",
        "validate": _validate_successfactors,
        "output_file": "successfactors/successfactors_companies.csv",
        "skip_slugs": set(),
    },
    "taleo": {
        # Taleo TBE: the "slug" is the full search-results URL because
        # the shard (`phe`/`phh`/...), instance number, ORG, and CWS all
        # vary per tenant. Same convention as Workday.
        "patterns": [
            r"https?://(?P<slug>ph[a-z]\.tbe\.taleo\.net/ph[a-z]\d+/ats/careers/v2/searchResults\?org=[A-Z0-9]+&cws=\d+)",
        ],
        "marketing": [],
        "search_domain": "tbe.taleo.net",
        # Slug already contains the full URL — special-cased like workday.
        "validate_url": "https://{slug}",
        "validate": _validate_taleo,
        "output_file": "taleo/taleo_companies.csv",
        "skip_slugs": set(),
        # Taleo URLs have case-sensitive path (`searchResults`) and ORG
        # codes (e.g. `THEBRIDG12`). Lowercasing breaks the API.
        "preserve_case": True,
    },
    "eightfold": {
        # Most Eightfold tenants live on `{slug}.eightfold.ai`. A handful
        # (Microsoft, ...) front the API on a custom domain — those won't
        # match this regex and need to be hand-curated in the CSV.
        "patterns": [r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.eightfold\.ai"],
        "marketing": [
            "https://eightfold.ai",
            "https://www.eightfold.ai",
        ],
        "search_domain": "eightfold.ai",
        # The `domain` query param expects the tenant's primary marketing
        # domain (e.g. `nvidia.com` for nvidia.eightfold.ai). Not all slugs
        # match `{slug}.com` — for those, validation fails benignly here
        # and the entry can be added manually with the correct domain.
        "validate_url": (
            "https://{slug}.eightfold.ai/api/pcsx/search"
            "?domain={slug}.com&query=&location=&start=0&sort_by=timestamp"
        ),
        "validate": _validate_eightfold,
        "output_file": "eightfold/eightfold_companies.csv",
        "skip_slugs": {
            "www", "api", "blog", "support", "help", "docs", "info",
            "developers", "developer", "partners", "partner", "customers",
            "learn", "talent", "marketing", "careers", "career",
        },
    },
    "pinpoint": {
        # Pinpoint tenants live at `{slug}.pinpointhq.com`. Marketing site
        # has a customer wall, but most leads come from SerpAPI `site:`.
        "patterns": [r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.pinpointhq\.com"],
        "marketing": ["https://www.pinpointhq.com", "https://pinpointhq.com"],
        "search_domain": "pinpointhq.com",
        "validate_url": "https://{slug}.pinpointhq.com/postings.json",
        "validate": _validate_pinpoint,
        "output_file": "pinpoint/pinpoint_companies.csv",
        "skip_slugs": {
            "www", "api", "developers", "developer", "support", "help",
            "blog", "docs", "marketing", "info", "go", "workwithus",
            "status", "app", "apps",
        },
    },
    "recruiterbox": {
        # Recruiterbox/Trakstar Hire posts live on `{slug}.hire.trakstar.com`
        # (canonical) and historically `recruiterbox.com/careers/{slug}`.
        # Both forms surface the same `client_name` in the JS-API URL.
        "patterns": [
            r"https?://(?P<slug>[a-z0-9][a-z0-9-]{0,62})\.hire\.trakstar\.com",
            r"https?://(?:www\.)?recruiterbox\.com/careers/(?P<slug>[a-z0-9][a-z0-9-]{0,62})",
        ],
        "marketing": [
            "https://www.trakstar.com",
            "https://hire.trakstar.com",
            "https://www.recruiterbox.com",
        ],
        "search_domain": "hire.trakstar.com",
        "validate_url": "https://jsapi.recruiterbox.com/v1/openings?client_name={slug}&limit=1",
        "validate": _validate_recruiterbox,
        "output_file": "recruiterbox/recruiterbox_companies.csv",
        "skip_slugs": {
            "www", "api", "support", "help", "blog", "developer",
            "developers", "marketing", "demoaccount", "test",
        },
    },
    "workday": {
        "patterns": [
            # Negative lookahead skips locale/system paths that aren't real
            # board names: ``en-US``/``en-GB``/``fr-CA``/etc., plus ``wday``,
            # ``pages``, ``static``, ``assets``, ``api``. Without this filter
            # the regex captures e.g. ``analogdevices.wd1.myworkdayjobs.com/en-US``
            # which doesn't validate as a real board.
            r"https?://(?P<slug>[a-z0-9][a-z0-9-]+\.wd\d+\.myworkdayjobs\.com/"
            r"(?!(?:en|fr|es|de|it|pt|ja|ko|zh|nl|pl|tr|ru|ar)-[A-Za-z]{2}(?:[/?#]|$))"
            r"(?!(?:wday|pages|static|assets|api|public|signup|login)(?:[/?#]|$))"
            r"[a-zA-Z0-9_-]+)",
        ],
        "marketing": [],
        "search_domain": "myworkdayjobs.com",
        "validate_url": "https://{slug}/jobs",  # special-cased: full URL is the slug
        "validate": _validate_workday,
        "output_file": "workday/workday_companies.csv",
        "skip_slugs": set(),
    },
}


# ---------------------------------------------------------------- backends --


async def firecrawl_search(
    client: httpx.AsyncClient, key: str, query: str, *, limit: int = 50
) -> list[str]:
    try:
        r = await client.post(
            "https://api.firecrawl.dev/v1/search",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"query": query, "limit": limit},
            timeout=30,
        )
    except httpx.HTTPError:
        return []
    if r.status_code != 200:
        return []
    try:
        items = r.json().get("data") or []
    except ValueError:
        return []
    out: list[str] = []
    for item in items:
        if isinstance(item, dict):
            for k in ("url", "link"):
                v = item.get(k)
                if isinstance(v, str):
                    out.append(v)
                    break
    return out


async def firecrawl_map(client: httpx.AsyncClient, key: str, url: str) -> list[str]:
    try:
        r = await client.post(
            "https://api.firecrawl.dev/v1/map",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"url": url, "limit": 5000},
            timeout=120,
        )
    except httpx.HTTPError:
        return []
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except ValueError:
        return []
    links = data.get("links") or data.get("data") or []
    if not isinstance(links, list):
        return []
    return [link for link in links if isinstance(link, str)]


async def serpapi_search(
    client: httpx.AsyncClient, key: str, query: str, *, num: int = 100
) -> list[str]:
    try:
        r = await client.get(
            "https://serpapi.com/search.json",
            params={"q": query, "engine": "google", "num": num, "api_key": key},
            timeout=30,
        )
    except httpx.HTTPError:
        return []
    if r.status_code != 200:
        return []
    try:
        data = r.json()
    except ValueError:
        return []
    return [
        result["link"]
        for result in (data.get("organic_results") or [])
        if isinstance(result, dict) and isinstance(result.get("link"), str)
    ]


async def github_code_search(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    *,
    pages: int = 10,
) -> list[str]:
    """GitHub /search/code with ``Accept: text-match`` so each result
    carries the actual matched fragment. Each fragment is one or more
    lines containing the search term — perfect for slug extraction.

    GitHub caps the search API at 1000 results per query (10 pages of
    100). We iterate up to ``pages`` and stop early on empty or rate-limit.

    Caller passes the token and the query; we return raw text fragments.
    The caller's regex extracts slugs.
    """
    out: list[str] = []
    for page in range(1, pages + 1):
        try:
            r = await client.get(
                "https://api.github.com/search/code",
                params={"q": query, "per_page": 100, "page": page},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github.v3.text-match+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30,
            )
        except httpx.HTTPError:
            break
        if r.status_code == 422:
            # GitHub returns 422 once we walk past the 1000-result cap.
            break
        if r.status_code == 403:
            # Rate-limit — back off and stop.
            await asyncio.sleep(2.0)
            break
        if r.status_code != 200:
            break
        try:
            data = r.json()
        except ValueError:
            break
        items = data.get("items") or []
        if not items:
            break
        for item in items:
            for tm in item.get("text_matches", []) or []:
                frag = tm.get("fragment")
                if isinstance(frag, str):
                    out.append(frag)
        # Search API rate limit is 30 req/min — pace ourselves.
        await asyncio.sleep(2.0)
    return out


async def searxng_search(
    client: httpx.AsyncClient, base: str, query: str, *, pages: int = 3
) -> list[str]:
    out: list[str] = []
    for page in range(1, pages + 1):
        try:
            r = await client.get(
                f"{base.rstrip('/')}/search",
                params={"q": query, "format": "json", "pageno": page},
                timeout=15,
            )
        except httpx.HTTPError:
            break
        if r.status_code != 200:
            break
        try:
            data = r.json()
        except ValueError:
            break
        results = data.get("results") or []
        if not results:
            break
        for result in results:
            if isinstance(result, dict) and isinstance(result.get("url"), str):
                out.append(result["url"])
    return out


# ------------------------------------------------------------- query banks --

INDUSTRIES = [
    "tech", "fintech", "saas", "ecommerce", "logistics", "retail",
    "healthcare", "biotech", "manufacturing", "education", "marketing",
    "consulting", "agency", "media", "construction", "automotive",
    "energy", "renewable", "real estate", "hospitality", "transport",
    "food", "fashion", "gaming", "cybersecurity", "aerospace",
    "ai", "ml", "robotics", "agritech", "edtech", "proptech",
    "crypto", "telco", "insurance", "pharma", "legal",
]
COUNTRIES = [
    "Netherlands", "Germany", "France", "Belgium", "Spain", "Italy",
    "Sweden", "Norway", "Finland", "Denmark", "Poland", "Austria",
    "Portugal", "Switzerland", "Ireland", "United Kingdom", "Czech Republic",
    "Romania", "Hungary", "Greece", "Canada", "Australia",
    "Estonia", "Lithuania", "Latvia", "Slovakia", "Slovenia",
    "Bulgaria", "Croatia", "Luxembourg", "Singapore", "Israel",
    "United States", "Brazil", "Mexico", "South Africa", "Japan",
]
KEYWORDS = ["careers", "jobs", "hiring", "apply", "open positions"]


def build_github_queries(domain: str) -> list[str]:
    """GitHub code-search queries for a single ATS host pattern.

    Empirically the /search/code endpoint returns the same top-1000
    results across most extension/language filters (they narrow but
    the ranking pinned to the same popular files). Adding context
    keywords like "careers" surfaces a *different* slice — that's
    where new tenants come from. Trimmed to high-yield variants only.
    """
    return [
        f'"{domain}"',
        f'"{domain}" careers',
        f'"{domain}" apply',
        f'"{domain}" hiring',
        f'"{domain}" jobs',
        f'"{domain}" link',
        f'"{domain}" href',
    ]


def build_serp_queries(domain: str) -> list[str]:
    base = [
        f"site:{domain}",
        f"site:{domain} careers",
        f"site:{domain} jobs",
        f"site:{domain} hiring",
        f"site:{domain} apply",
        f"site:{domain} open positions",
    ]
    base.extend(f"site:{domain} {kw}" for kw in ["engineer", "manager", "developer", "designer", "sales"])
    return base


def build_search_queries(domain: str, max_queries: int) -> list[str]:
    queries: list[str] = []
    for ind, kw in product(INDUSTRIES, KEYWORDS[:3]):
        queries.append(f"{domain} {kw} {ind}")
    for country, kw in product(COUNTRIES, KEYWORDS[:2]):
        queries.append(f"{domain} {kw} {country}")
    queries.append(f'"powered by {domain}"')
    queries.append(f'"hiring on {domain}"')
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            out.append(q)
        if len(out) >= max_queries:
            break
    return out


# ----------------------------------------------------------------- helpers --


def extract_slugs(
    urls: list[str],
    patterns: list[re.Pattern[str]],
    skip: set[str],
    *,
    preserve_case: bool = False,
) -> set[str]:
    """Extract slugs matching `patterns` from `urls`.

    Lowercases slugs by default — Greenhouse/Lever/etc. tenants are
    case-insensitive at the API level. Pass `preserve_case=True` for
    platforms whose URLs encode case-sensitive data (Taleo's
    ``searchResults`` path; Oracle's ``CX_45002`` site numbers; etc.)."""
    found: set[str] = set()
    for url in urls:
        if not isinstance(url, str):
            continue
        for pat in patterns:
            for m in pat.finditer(url):
                slug = m.group("slug")
                if not preserve_case:
                    slug = slug.lower()
                if slug and slug not in skip:
                    found.add(slug)
    return found


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def existing_slugs_from_csv(path: Path, patterns: list[re.Pattern[str]]) -> dict[str, str]:
    """Return ``slug -> name`` from an existing CSV (``name,url``).

    Accepts three CSV-row shapes that have appeared in this repo over time:

    1. ``url`` is a full HTTP URL → run platform regex against it.
    2. ``url`` is the bare slug (post-linter rewrite) → take it as-is.
    3. ``url`` is missing or empty → fall back to ``name`` as the slug.

    Without this fallback, future discovery runs read 0 existing tenants
    and silently overwrite the CSV with only newly-discovered slugs —
    erasing battle-tested tenants in the process. We saw this break
    recruiterbox (212 → 41) and iCIMS (545 → 545 by coincidence).
    """
    out: dict[str, str] = {}
    if not path.exists():
        return out
    with path.open() as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if not row:
                continue
            name = row[0].strip() if row else ""
            url = row[1].strip() if len(row) > 1 else ""
            slug: str | None = None
            # Shape 1: URL → regex match
            if url.startswith("http"):
                for pat in patterns:
                    m = pat.search(url)
                    if m:
                        slug = m.group("slug").lower()
                        break
                if slug is None:
                    # URL doesn't match — but it IS a URL. Use the name as
                    # a last resort so we don't lose the row.
                    slug = name.lower() or None
            # Shape 2: bare slug in url column
            elif url:
                slug = url.lower()
            # Shape 3: only name
            elif name:
                slug = name.lower()
            if slug:
                out[slug] = name or slug
    return out


# --------------------------------------------------------------- validate --


async def validate_slug(
    client: httpx.AsyncClient,
    slug: str,
    config: dict[str, Any],
    use_httpcloak: bool,
) -> tuple[str, int] | None:
    url = config["validate_url"].format(slug=slug)
    validate_fn: Callable[[httpx.Response], tuple[str, int] | None] | None = config.get("validate")
    if validate_fn is None:
        return None

    if use_httpcloak or config.get("client") == "httpcloak":
        try:
            import httpcloak
        except ImportError:
            return None
        # httpcloak is sync — run in executor to keep pipeline async
        loop = asyncio.get_running_loop()

        def call() -> tuple[int, str]:
            try:
                resp = httpcloak.get(
                    url,
                    timeout=15,
                    headers={"Accept": "application/json,text/html,*/*"},
                )
                return (resp.status_code, resp.text)
            except Exception:
                return (0, "")

        status, text = await loop.run_in_executor(None, call)

        # Wrap in a fake httpx.Response-like object for the validators
        class _FakeResp:
            def __init__(self, status: int, text: str) -> None:
                self.status_code = status
                self.text = text

            def json(self) -> Any:
                import json as _json

                return _json.loads(self.text)

        return validate_fn(_FakeResp(status, text))  # type: ignore[arg-type]

    try:
        r = await client.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/html,*/*"},
            timeout=15,
        )
    except httpx.HTTPError:
        return None
    return validate_fn(r)


# ------------------------------------------------------------------ pipeline --


async def discover_platform(
    platform: str,
    *,
    backends: list[str],
    max_queries: int,
    concurrency: int,
    use_httpcloak: bool,
    no_validate: bool,
) -> int:
    config = PLATFORMS[platform]
    patterns = [re.compile(p, re.IGNORECASE) for p in config["patterns"]]
    skip = config.get("skip_slugs") or set()
    preserve_case = bool(config.get("preserve_case"))
    output_path = REPO / config["output_file"]

    print(f"\n{'='*70}\nDiscovering {platform.upper()}\n{'='*70}")

    serp_key = os.getenv("SERPAPI_API_KEY")
    fc_key = os.getenv("FIRECRAWL_API_KEY")
    searxng_url = os.getenv("SEARXNG_URL")
    github_token = os.getenv("GITHUB_TOKEN")

    existing = existing_slugs_from_csv(output_path, patterns)
    print(f"  Existing CSV: {len(existing)} tenants at {output_path}")

    found: set[str] = set()
    started = datetime.now()

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Step 1 — Firecrawl /map on marketing sites
        if "map" in backends and fc_key and config.get("marketing"):
            for site in config["marketing"]:
                urls = await firecrawl_map(client, fc_key, site)
                slugs = extract_slugs(urls, patterns, skip, preserve_case=preserve_case)
                new = slugs - existing.keys() - found
                print(f"  [map ] {site:40s}  links={len(urls)}  +{len(new)} new")
                found.update(slugs)

        # Step 2 — SerpAPI
        if "serp" in backends and serp_key:
            queries = build_serp_queries(config["search_domain"])
            for q in queries:
                urls = await serpapi_search(client, serp_key, q)
                slugs = extract_slugs(urls, patterns, skip, preserve_case=preserve_case)
                new = slugs - existing.keys() - found
                if new:
                    print(f"  [serp] {q[:60]:60s}  +{len(new)} new")
                found.update(slugs)

        # Step 3 — Firecrawl /search
        if "fc-search" in backends and fc_key:
            queries = build_search_queries(config["search_domain"], max_queries)
            print(f"  [fc  ] running {len(queries)} parallel /search calls...")
            sem = asyncio.Semaphore(concurrency)

            async def fc_task(q: str) -> list[str]:
                async with sem:
                    return await firecrawl_search(client, fc_key, q)

            url_lists = await asyncio.gather(*(fc_task(q) for q in queries))
            for urls in url_lists:
                found.update(extract_slugs(urls, patterns, skip))

        # Step 3.5 — GitHub code search (high signal, capped 1000 results
        # per query — we run multiple variants to compound coverage).
        if "github" in backends and github_token:
            queries = build_github_queries(config["search_domain"])
            print(f"  [gh  ] running {len(queries)} GitHub code-search queries...")
            slug_pat = patterns[0] if patterns else None
            for q in queries:
                fragments = await github_code_search(client, github_token, q)
                slugs: set[str] = set()
                if slug_pat is not None:
                    for frag in fragments:
                        for m in slug_pat.finditer(frag):
                            try:
                                slug = m.group("slug")
                            except IndexError:
                                continue
                            if not preserve_case:
                                slug = slug.lower()
                            if slug and slug not in skip:
                                slugs.add(slug)
                new = slugs - existing.keys() - found
                print(f"  [gh  ] {q[:55]:55s}  +{len(new)} new")
                found.update(slugs)

        # Step 4 — SearXNG fallback (free, unlimited)
        if "searxng" in backends and searxng_url:
            try:
                ping = await client.head(searxng_url.rstrip("/"), timeout=5)
                reachable = ping.status_code < 500
            except httpx.HTTPError:
                reachable = False
            if reachable:
                queries = build_search_queries(config["search_domain"], max_queries)
                print(f"  [sxng] {searxng_url} — running {len(queries)} queries...")
                sem = asyncio.Semaphore(concurrency)

                async def sxng_task(q: str) -> list[str]:
                    async with sem:
                        return await searxng_search(client, searxng_url, q)

                url_lists = await asyncio.gather(*(sxng_task(q) for q in queries))
                for urls in url_lists:
                    found.update(extract_slugs(urls, patterns, skip, preserve_case=preserve_case))
            else:
                print(f"  [sxng] {searxng_url} unreachable — skipping")

        candidates = sorted(found - existing.keys())
        elapsed = (datetime.now() - started).total_seconds()
        print(f"\n  Discovery: {len(found)} unique slugs total, {len(candidates)} new, {elapsed:.0f}s")

        if not candidates:
            print("  Nothing new to validate.")
            return 0

        if no_validate:
            valid = {slug: ("", 0) for slug in candidates}
        else:
            # Two-pass validation. Pass 1 is fast and wide; pass 2 re-checks
            # the failures at low concurrency with retries to weed out
            # rate-limit false negatives. A candidate must clear at least
            # one pass to be added — we never write a 404 to the CSV.
            print(f"  Validating {len(candidates)} candidates (two-pass)...")
            valid: dict[str, tuple[str, int]] = {}
            sem_fast = asyncio.Semaphore(concurrency)

            async def vtask_fast(slug: str) -> tuple[str, tuple[str, int] | None]:
                async with sem_fast:
                    try:
                        return slug, await validate_slug(
                            client, slug, config, use_httpcloak
                        )
                    except Exception:
                        return slug, None

            results = await asyncio.gather(*(vtask_fast(s) for s in candidates))
            suspect: list[str] = []
            for slug, res in results:
                if res is not None:
                    valid[slug] = res
                else:
                    suspect.append(slug)

            if suspect:
                slow_concurrency = max(2, concurrency // 4)
                sem_slow = asyncio.Semaphore(slow_concurrency)
                print(
                    f"  Pass 1: {len(valid)} confirmed alive, "
                    f"{len(suspect)} suspect — re-checking at concurrency="
                    f"{slow_concurrency} with 3 retries each"
                )

                async def vtask_slow(slug: str) -> tuple[str, tuple[str, int] | None]:
                    last: tuple[str, int] | None = None
                    for attempt in range(1, 4):
                        async with sem_slow:
                            try:
                                last = await validate_slug(
                                    client, slug, config, use_httpcloak
                                )
                            except Exception:
                                last = None
                        if last is not None:
                            return slug, last
                        await asyncio.sleep(1.0 * attempt)
                    return slug, None

                results2 = await asyncio.gather(*(vtask_slow(s) for s in suspect))
                for slug, res in results2:
                    if res is not None:
                        valid[slug] = res

            kept_pct = len(valid) * 100 // max(len(candidates), 1)
            print(
                f"  Validated: {len(valid)}/{len(candidates)} ({kept_pct}%) — "
                f"{len(candidates) - len(valid)} confirmed dead, never written"
            )

    # Merge into output CSV (always additive)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged: dict[str, str] = dict(existing)
    new_count = 0
    for slug, (name, _) in valid.items():
        if slug not in merged:
            new_count += 1
        merged[slug] = name or slug

    with output_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "url"])
        for slug, name in sorted(merged.items()):
            url = config["validate_url"].format(slug=slug).split("/api/")[0].split("?")[0]
            # Prefer the canonical careers URL, not the API URL
            if "{slug}" in (config.get("validate_url") or ""):
                # Reconstruct from validate_url's host portion
                pass
            # Build a public URL based on platform pattern
            url = _public_url_for(platform, slug)
            writer.writerow([name or slug, url])

    print(f"\n  Wrote: {output_path}  ({len(merged)} tenants total, +{new_count} new)")
    return new_count


def _public_url_for(platform: str, slug: str) -> str:
    """Return the canonical public careers URL for a tenant slug."""
    return {
        "recruitee": f"https://{slug}.recruitee.com",
        "bamboohr": f"https://{slug}.bamboohr.com/careers",
        "teamtailor": f"https://{slug}.teamtailor.com",
        "jazzhr": f"https://{slug}.applytojob.com",
        "lever": f"https://jobs.lever.co/{slug}",
        "greenhouse": f"https://job-boards.greenhouse.io/{slug}",
        "ashby": f"https://jobs.ashbyhq.com/{slug}",
        "workable": f"https://apply.workable.com/{slug}",
        "smartrecruiters": f"https://jobs.smartrecruiters.com/{slug}",
        "rippling": f"https://ats.rippling.com/{slug}/jobs",
        "personio": f"https://{slug}.jobs.personio.com",
        "workday": f"https://{slug}",  # slug is already a full URL for workday
    }.get(platform, slug)


# ------------------------------------------------------------------ CLI ----


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "platform",
        nargs="?",
        choices=sorted(PLATFORMS.keys()),
        help="ATS to discover (omit with --all to run every platform)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run discovery for every configured platform",
    )
    parser.add_argument(
        "--backend",
        default="map,serp,fc-search,searxng,github",
        help="Comma-separated backends to enable: map, serp, fc-search, searxng",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=80,
        help="Cap on search queries per backend (default: 80)",
    )
    parser.add_argument("--concurrency", type=int, default=15)
    parser.add_argument(
        "--httpcloak",
        action="store_true",
        help="Force httpcloak for validation (auto-enabled for some platforms)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip the per-tenant validation step (write all candidates as-is)",
    )
    args = parser.parse_args()

    if not args.platform and not args.all:
        parser.print_help()
        return 1
    targets = sorted(PLATFORMS.keys()) if args.all else [args.platform]
    backends = [b.strip() for b in args.backend.split(",") if b.strip()]

    load_dotenv(REPO / ".env")
    if not (os.getenv("FIRECRAWL_API_KEY") or os.getenv("SERPAPI_API_KEY") or os.getenv("SEARXNG_URL")):
        print("Need at least one of FIRECRAWL_API_KEY / SERPAPI_API_KEY / SEARXNG_URL", file=sys.stderr)
        return 1

    total_new = 0
    for platform in targets:
        try:
            total_new += asyncio.run(
                discover_platform(
                    platform,
                    backends=backends,
                    max_queries=args.max_queries,
                    concurrency=args.concurrency,
                    use_httpcloak=args.httpcloak,
                    no_validate=args.no_validate,
                )
            )
        except KeyboardInterrupt:
            print("Interrupted")
            return 130

    print(f"\n{'='*70}\nGrand total: +{total_new} new tenants across {len(targets)} platform(s)\n{'='*70}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
