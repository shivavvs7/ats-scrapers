#!/usr/bin/env python3
"""
Continuous Discovery Loop for All ATS Platforms

Runs discovery across all platforms in cycles, progressively finding more companies.
Uses the local SearXNG instance for unlimited queries.

Features:
- Runs all platforms in sequence
- Configurable number of cycles
- Progressive search (starts with broad queries, gets more specific)
- Tracks progress and statistics
- Saves results after each platform
- Logs discoveries to file
"""

import time
import logging
import sys
from datetime import datetime
from pathlib import Path

try:
    from searxng_discovery import discover_platform, PLATFORMS
except ImportError:
    print("Error: Could not import searxng_discovery module")
    sys.exit(1)

# Configuration (can be overridden via CLI args)
CYCLES = 5
QUERIES_PER_CYCLE = 20
PAGES_PER_QUERY = 5
DELAY_BETWEEN_PAGES = 0.5
DELAY_BETWEEN_PLATFORMS = 10
DELAY_BETWEEN_CYCLES = 60


def setup_logging():
    """Setup logging to file and console"""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"discovery_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return log_file


def run_discovery_cycle(
    cycle_num: int,
    queries_per_platform: int,
    pages_per_query: int,
    delay_between_pages: float,
    delay_between_platforms: float,
):
    """Run one complete cycle through all platforms"""
    
    stats = {
        "cycle": cycle_num,
        "platforms": {},
        "total_new": 0,
        "start_time": datetime.now(),
    }
    
    platform_list = list(PLATFORMS.keys())
    
    for idx, platform_name in enumerate(platform_list, 1):
        logging.info(f"\n[Cycle {cycle_num}] Platform {idx}/{len(platform_list)}: {platform_name.upper()}")
        
        try:
            # Calculate query offset for progressive discovery
            # Each cycle starts from a different point in the search strategies
            query_offset = (cycle_num - 1) * queries_per_platform
            
            # Run discovery for this platform
            discover_platform(
                platform_name=platform_name,
                max_queries=queries_per_platform,
                pages_per_query=pages_per_query,
                engines="yahoo,bing",
                request_delay=delay_between_pages,
                use_cloud=False,
                local_only=True,
                min_instance_cooldown=30.0,
            )
            
            stats["platforms"][platform_name] = "completed"
            
        except KeyboardInterrupt:
            logging.warning(f"\n⚠️  Interrupted during {platform_name}")
            raise
        except Exception as e:
            logging.error(f"Error discovering {platform_name}: {e}")
            stats["platforms"][platform_name] = f"error: {str(e)[:100]}"
        
        # Delay between platforms
        if idx < len(platform_list):
            logging.info(f"⏳ Waiting {delay_between_platforms}s before next platform...")
            time.sleep(delay_between_platforms)
    
    stats["end_time"] = datetime.now()
    stats["duration"] = (stats["end_time"] - stats["start_time"]).total_seconds()
    
    return stats


def main(
    cycles: int,
    queries_per_platform: int,
    pages_per_query: int,
    delay_between_pages: float,
    delay_between_platforms: float,
    delay_between_cycles: float,
):
    """Main continuous discovery loop"""
    
    log_file = setup_logging()
    
    logging.info("=" * 80)
    logging.info("🔄 CONTINUOUS DISCOVERY STARTED")
    logging.info("=" * 80)
    logging.info(f"Cycles: {cycles}")
    logging.info(f"Platforms per cycle: {len(PLATFORMS)}")
    logging.info(f"Queries per platform: {queries_per_platform}")
    logging.info(f"Pages per query: {pages_per_query}")
    logging.info(f"Delay between pages: {delay_between_pages}s")
    logging.info(f"Delay between platforms: {delay_between_platforms}s")
    logging.info(f"Delay between cycles: {delay_between_cycles}s")
    logging.info(f"Log file: {log_file}")
    logging.info("=" * 80)
    logging.info(f"\nPlatforms: {', '.join(PLATFORMS.keys())}")
    logging.info("=" * 80)
    
    all_stats = []
    total_start = datetime.now()
    
    try:
        for cycle in range(1, cycles + 1):
            logging.info(f"\n{'='*80}")
            logging.info(f"🔄 STARTING CYCLE {cycle}/{cycles}")
            logging.info(f"{'='*80}")
            
            cycle_stats = run_discovery_cycle(
                cycle_num=cycle,
                queries_per_platform=queries_per_platform,
                pages_per_query=pages_per_query,
                delay_between_pages=delay_between_pages,
                delay_between_platforms=delay_between_platforms,
            )
            
            all_stats.append(cycle_stats)
            
            logging.info(f"\n{'='*80}")
            logging.info(f"✅ CYCLE {cycle}/{cycles} COMPLETED")
            logging.info(f"Duration: {cycle_stats['duration']:.1f}s ({cycle_stats['duration']/60:.1f} minutes)")
            logging.info(f"Platforms completed: {sum(1 for v in cycle_stats['platforms'].values() if v == 'completed')}/{len(PLATFORMS)}")
            logging.info(f"{'='*80}")
            
            # Delay between cycles
            if cycle < cycles:
                logging.info(f"\n⏳ Waiting {delay_between_cycles}s before next cycle...")
                time.sleep(delay_between_cycles)
    
    except KeyboardInterrupt:
        logging.warning("\n\n⚠️  Discovery interrupted by user")
        logging.info(f"Completed {len(all_stats)} out of {cycles} cycles")
    
    total_duration = (datetime.now() - total_start).total_seconds()
    
    # Final summary
    logging.info("\n" + "=" * 80)
    logging.info("🎉 CONTINUOUS DISCOVERY COMPLETED")
    logging.info("=" * 80)
    logging.info(f"Total cycles completed: {len(all_stats)}/{cycles}")
    logging.info(f"Total platforms per cycle: {len(PLATFORMS)}")
    logging.info(f"Total duration: {total_duration:.1f}s ({total_duration/60:.1f} minutes)")
    logging.info(f"Average per cycle: {total_duration/len(all_stats):.1f}s" if all_stats else "N/A")
    logging.info(f"Log file: {log_file}")
    logging.info("=" * 80)
    
    # Summary by platform
    logging.info("\n📊 Platform Summary:")
    for platform in PLATFORMS.keys():
        completed_cycles = sum(
            1 for stat in all_stats 
            if stat["platforms"].get(platform) == "completed"
        )
        logging.info(f"  {platform}: {completed_cycles}/{len(all_stats)} cycles completed")
    
    logging.info("\n" + "=" * 80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Continuous discovery loop for all ATS platforms",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 5 cycles with default settings (20 queries, 5 pages each)
  python continuous_discovery.py
  
  # Run 10 cycles with more queries
  python continuous_discovery.py --cycles 10 --queries 30 --pages 7
  
  # Quick test run (1 cycle, fewer queries)
  python continuous_discovery.py --cycles 1 --queries 5 --pages 2
  
  # Long-running discovery (overnight)
  nohup python continuous_discovery.py --cycles 20 --queries 50 --pages 10 > discovery.log 2>&1 &
  
  # Aggressive discovery (more pages, less delay)
  python continuous_discovery.py --cycles 5 --queries 30 --pages 10 --delay 0.3
        """
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=5,
        help="Number of cycles to run (default: 5)",
    )
    parser.add_argument(
        "--queries",
        type=int,
        default=20,
        help="Queries per platform per cycle (default: 20)",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="Pages per query (default: 5)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.5,
        help="Seconds between page requests (default: 0.5)",
    )
    parser.add_argument(
        "--platform-delay",
        type=float,
        default=10.0,
        help="Seconds between platforms (default: 10)",
    )
    parser.add_argument(
        "--cycle-delay",
        type=float,
        default=60.0,
        help="Seconds between cycles (default: 60)",
    )
    
    args = parser.parse_args()
    
    main(
        cycles=args.cycles,
        queries_per_platform=args.queries,
        pages_per_query=args.pages,
        delay_between_pages=args.delay,
        delay_between_platforms=args.platform_delay,
        delay_between_cycles=args.cycle_delay,
    )
