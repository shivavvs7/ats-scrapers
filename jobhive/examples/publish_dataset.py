"""Publish the local repo's CSVs to Cloudflare R2.

Set the four CLOUDFLARE_* environment variables first.
"""

from pathlib import Path

from jobhive.storage import DatasetPublisher, R2Client, R2Config

repo_root = Path(__file__).resolve().parents[2]

r2 = R2Client(R2Config.from_env())
publisher = DatasetPublisher(r2)

result = publisher.publish_from_directory(
    source_dir=repo_root,
    ats_csv_pattern="{ats}/jobs.csv",
    dated_snapshots=sorted(repo_root.glob("ai-*.csv")),
)

print(f"Published {result.total_jobs:,} jobs in {result.duration_seconds:.1f}s")
print(f"Manifest: {result.manifest_key}")
