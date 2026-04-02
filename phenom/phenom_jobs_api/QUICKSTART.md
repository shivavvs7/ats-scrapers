# Quick Start Guide

Get started with the Phenom Jobs API Client in 60 seconds!

## Installation

```bash
# No installation needed! Just requires Python 3.6+ and requests
pip install requests
```

## 30-Second Example

```python
from api_client import PhenomJobsClient

# Initialize for Bell Canada
client = PhenomJobsClient(
    base_url="https://jobs.bell.ca",
    company_code="BECACA",
    locale="en_ca",
    country="ca"
)

# Get all jobs (auto-pagination!)
jobs = client.get_all_jobs(max_results=50)

# Print results
for job in jobs:
    print(f"{job['title']} - {job['location']}")
```

## Run the Examples

```bash
# Run built-in examples
python3 api_client.py

# Run test suite
python3 test_api.py
```

## Common Use Cases

### Search by Keyword

```python
results = client.search_jobs(keywords="software engineer", size=10)
jobs = client._extract_jobs(results)
```

### Filter by Location and Category

```python
results = client.search_jobs(
    keywords="data scientist",
    category="Technology",
    filters={"state": ["Ontario"]}
)
```

### Export to CSV

```python
import csv

jobs = client.get_all_jobs()
with open('jobs.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=jobs[0].keys())
    writer.writeheader()
    writer.writerows(jobs)
```

### Use with Different Companies

```python
# GE Healthcare
ge_client = PhenomJobsClient(
    base_url="https://careers.gehealthcare.com",
    company_code="GEVGHLGLOBAL",
    locale="en_global",
    country="global"
)

jobs = ge_client.get_all_jobs()
```

## Documentation

- **README.md** - Full API documentation and usage guide
- **SUMMARY.md** - Technical details about API discovery
- **api_client.py** - Source code with inline documentation

## Support

For detailed documentation, see README.md

For technical details about the API, see SUMMARY.md

For examples, run: `python3 api_client.py`
