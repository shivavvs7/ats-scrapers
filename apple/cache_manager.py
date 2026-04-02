#!/usr/bin/env python3
"""
Cache Manager for Apple Job Descriptions

Manages a persistent cache of job descriptions to avoid refetching them.
- Stores detailed job information (description, qualifications, etc.)
- Automatically cleans up entries for deleted jobs
- Indexed by positionId for fast lookups
"""

import json
from pathlib import Path
from typing import Dict, Set, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class JobDescriptionCache:
    """Manages caching of job descriptions to avoid redundant API calls."""

    def __init__(self, cache_path: Optional[str] = None):
        """
        Initialize the cache manager.

        Args:
            cache_path: Path to the cache file. Defaults to job_details_cache.json
        """
        if cache_path is None:
            script_dir = Path(__file__).resolve().parent
            cache_path = str(script_dir / "job_details_cache.json")

        self.cache_path = cache_path
        self.cache: Dict[str, dict] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from disk if it exists."""
        try:
            if Path(self.cache_path).exists():
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.cache = data.get('cache', {})
                    last_updated = data.get('last_updated', 'unknown')
                    logger.info(f"Loaded cache with {len(self.cache)} entries (last updated: {last_updated})")
            else:
                logger.info("No existing cache found, starting fresh")
                self.cache = {}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load cache: {e}. Starting with empty cache.")
            self.cache = {}

    def save_cache(self) -> None:
        """Save cache to disk."""
        try:
            data = {
                'last_updated': datetime.now().isoformat(),
                'cache': self.cache
            }
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved cache with {len(self.cache)} entries to {self.cache_path}")
        except OSError as e:
            logger.error(f"Failed to save cache: {e}")

    def get(self, position_id: str) -> Optional[dict]:
        """
        Get cached job details by position ID.

        Args:
            position_id: The job's position ID

        Returns:
            Cached job details dict or None if not cached
        """
        return self.cache.get(position_id)

    def set(self, position_id: str, description: str, min_qualifications: str,
            pref_qualifications: str, pay_benefits: Optional[str]) -> None:
        """
        Cache job details for a position.

        Args:
            position_id: The job's position ID
            description: Full job description
            min_qualifications: Minimum qualifications
            pref_qualifications: Preferred qualifications
            pay_benefits: Pay and benefits info (optional)
        """
        self.cache[position_id] = {
            'description': description,
            'minimumQualifications': min_qualifications,
            'preferredQualifications': pref_qualifications,
            'payAndBenefits': pay_benefits,
            'cached_at': datetime.now().isoformat()
        }

    def has(self, position_id: str) -> bool:
        """Check if a position is in the cache."""
        return position_id in self.cache

    def cleanup_deleted_jobs(self, current_position_ids: Set[str]) -> int:
        """
        Remove cache entries for jobs that no longer exist.

        Args:
            current_position_ids: Set of position IDs that currently exist

        Returns:
            Number of entries removed
        """
        cached_ids = set(self.cache.keys())
        deleted_ids = cached_ids - current_position_ids

        for position_id in deleted_ids:
            del self.cache[position_id]

        if deleted_ids:
            logger.info(f"Cleaned up {len(deleted_ids)} deleted job entries from cache")

        return len(deleted_ids)

    def get_cache_stats(self) -> dict:
        """Get statistics about the cache."""
        return {
            'total_entries': len(self.cache),
            'cache_path': self.cache_path
        }

    def __len__(self) -> int:
        """Return number of cached entries."""
        return len(self.cache)
