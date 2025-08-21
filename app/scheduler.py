#!/usr/bin/env python3
"""
AIVO Scheduler - Runs hourly aggregation jobs
This script should be run as a cron job every hour to process completed transcript chunks.
"""

import logging
import schedule
import time
from datetime import datetime, timezone
from .job import process_pending_hourly_records

# Configure logging for scheduler
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - (AIVO-Scheduler) - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("./logs/aivo-scheduler.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)


def run_hourly_aggregation():
    """Run the hourly aggregation job."""
    try:
        logger.info("🔄 Starting hourly aggregation job...")
        start_time = datetime.now(timezone.utc)

        process_pending_hourly_records()

        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        logger.info(f"✅ Hourly aggregation completed in {duration:.2f} seconds")

    except Exception as e:
        logger.error(f"❌ Hourly aggregation failed: {e}", exc_info=True)


def main():
    """Main scheduler function."""
    logger.info("🚀 Starting AIVO Scheduler...")

    # Schedule hourly job at the top of each hour
    schedule.every().hour.at(":05").do(run_hourly_aggregation)

    # Run immediately on startup to catch any missed hours
    logger.info("🔄 Running initial aggregation check...")
    run_hourly_aggregation()

    logger.info("⏰ Scheduler active - waiting for scheduled jobs...")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("⏹️ Scheduler stopped by user")
    except Exception as e:
        logger.error(f"❌ Scheduler error: {e}")
        raise
