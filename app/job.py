import logging
from datetime import datetime, timezone
from sqlalchemy import and_
from .db import SessionLocal, HourlyRecord, TranscriptChunk, StatusEnum
from .utils import get_ai_insights

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - (AIVO-Aggregator) - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def process_pending_hourly_records():
    """Process all pending hourly records that are in PROCESSING status."""
    with SessionLocal() as db:
        start_of_current_hour = datetime.now(timezone.utc).replace(
            minute=0, second=0, microsecond=0
        )
        pending_records = (
            db.query(HourlyRecord)
            .filter(
                and_(
                    HourlyRecord.status == StatusEnum.PROCESSING,
                    HourlyRecord.hour_start_time < start_of_current_hour,
                )
            )
            .all()
        )

        if not pending_records:
            logging.info("No pending hourly records to process. All up to date.")
            return

        logging.info("Found %d hourly records to process.", len(pending_records))

        for record in pending_records:
            logging.info(
                "Processing record for hour: %s",
                record.hour_start_time.strftime("%Y-%m-%d %H:00"),
            )
            try:
                chunks = (
                    db.query(TranscriptChunk)
                    .filter(TranscriptChunk.hourly_record_id == record.id)
                    .order_by(TranscriptChunk.start_time)
                    .all()
                )

                if not chunks:
                    logging.warning(
                        "HourlyRecord %s has no chunks. Marking as COMPLETED.", record.id
                    )
                    record.status = StatusEnum.COMPLETED
                    db.commit()
                    continue

                full_transcript = " ".join(
                    chunk.transcript for chunk in chunks if chunk.transcript
                )
                record.full_transcript = full_transcript

                insights = get_ai_insights(full_transcript)

                record.summary = insights.get(
                    "summary", "AI summary failed or was not provided."
                )
                record.overview = insights.get("overview", "")
                record.keywords = insights.get("keywords", [])
                record.status = StatusEnum.COMPLETED
                record.updated_at = datetime.now(timezone.utc)

                db.commit()
                logging.info(
                    "✅ Successfully processed and completed HourlyRecord %s.", record.id
                )

            except Exception as e:
                db.rollback()
                logging.error(
                    "❌ Failed to process HourlyRecord %s. Setting status to ERROR. Error: %s",
                    record.id,
                    e,
                    exc_info=True,
                )
                db.query(HourlyRecord).filter(HourlyRecord.id == record.id).update(
                    {"status": StatusEnum.ERROR}
                )
                db.commit()
