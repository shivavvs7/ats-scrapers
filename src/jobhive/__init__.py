"""jobhive — open dataset and toolkit for global job market data.

Three layers of progressive disclosure:

1. Dataset client (zero config):
   >>> from jobhive import search
   >>> df = search(query="ml engineer", location="Paris")

2. Per-ATS scrapers (BYO companies):
   >>> from jobhive.scrapers import GreenhouseScraper
   >>> jobs = GreenhouseScraper("openai").fetch()

3. Full pipeline (discover + scrape + enrich + publish):
   >>> from jobhive import Pipeline
   >>> Pipeline().discover(ats="lever").scrape().to_csv("out.csv")
"""

from jobhive._version import __version__
from jobhive.client import Client, search
from jobhive.exceptions import (
    JobHiveError,
    ManifestError,
    ScraperError,
    StorageError,
)
from jobhive.manifest import Manifest
from jobhive.models import Company, Job, Salary

__all__ = [
    "Client",
    "Company",
    "Job",
    "JobHiveError",
    "Manifest",
    "ManifestError",
    "Salary",
    "ScraperError",
    "StorageError",
    "__version__",
    "search",
]
