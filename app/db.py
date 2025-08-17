"""
Module for managing the database connection and models using SQLAlchemy.
"""

import os
from datetime import datetime, timezone
from uuid import uuid4
from enum import Enum as PyEnum

from sqlalchemy import create_engine, Column, String, DateTime, ForeignKey, Enum, TEXT
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, ARRAY
from dotenv import load_dotenv

load_dotenv()
Base = declarative_base()

DATABASE_URL = os.getenv("DB_URL")
if not DATABASE_URL:
    raise ValueError("DB_URL environment variable is not set")

# Use a connection pool for efficiency
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ---- ENUMS ----
class StatusEnum(PyEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


# ---- MODELS ----
class Day(Base):
    __tablename__ = "days"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    day_date = Column(DateTime(timezone=True), nullable=False, unique=True)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    hourly_records = relationship(
        "HourlyRecord", back_populates="day", cascade="all, delete-orphan"
    )


class HourlyRecord(Base):
    __tablename__ = "hourly_records"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    day_id = Column(PG_UUID(as_uuid=True), ForeignKey("days.id"), nullable=False)

    hour_start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(Enum(StatusEnum), nullable=False, default=StatusEnum.PROCESSING)
    full_transcript = Column(
        TEXT, nullable=True
    )  # These fields will be populated by the aggregation job
    summary = Column(TEXT, nullable=True)
    overview = Column(TEXT, nullable=True)
    keywords = Column(ARRAY(String), nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    day = relationship("Day", back_populates="hourly_records")
    chunks = relationship(
        "TranscriptChunk", back_populates="hourly_record", cascade="all, delete-orphan"
    )


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    hourly_record_id = Column(
        PG_UUID(as_uuid=True), ForeignKey("hourly_records.id"), nullable=False
    )

    transcript = Column(TEXT, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    hourly_record = relationship("HourlyRecord", back_populates="chunks")


# -----------------------------
#   CORE DATABASE LOGIC
# -----------------------------


def save_transcript_chunk(
    transcript_text: str, start_time: datetime, end_time: datetime
):
    """
    Saves a transcribed chunk and handles the creation/linking of its
    parent Day and HourlyRecord. This is the main function for the recorder.
    """
    with SessionLocal() as db:
        try:
            # Find or Create the Day record
            day_date = start_time.date()
            day_record = db.query(Day).filter(Day.day_date == day_date).first()
            if not day_record:
                day_record = Day(day_date=day_date)
                db.add(day_record)
                db.flush()
                print(f"✅ Created new Day record for {day_date}")

            # Find or Create the HourlyRecord
            hour_start_time = start_time.replace(minute=0, second=0, microsecond=0)
            hourly_record = (
                db.query(HourlyRecord)
                .filter(
                    HourlyRecord.day_id == day_record.id,
                    HourlyRecord.hour_start_time == hour_start_time,
                )
                .first()
            )

            if not hourly_record:
                hourly_record = HourlyRecord(
                    day_id=day_record.id,
                    hour_start_time=hour_start_time,
                    status=StatusEnum.PROCESSING,
                )
                db.add(hourly_record)
                db.flush()  # Flush to get ID for the chunk
                print(
                    f"✅ Created new HourlyRecord for {hour_start_time.strftime('%Y-%m-%d %H:%M')}"
                )

            # Create the TranscriptChunk
            new_chunk = TranscriptChunk(
                hourly_record_id=hourly_record.id,
                transcript=transcript_text,
                start_time=start_time,
                end_time=end_time,
            )
            db.add(new_chunk)

            db.commit()
            print(
                f"✅ Successfully saved chunk from {start_time.strftime('%H:%M:%S')} to {end_time.strftime('%H:%M:%S')}"
            )
            return new_chunk
        except Exception as e:
            db.rollback()
            print(f"❌ Error in save_transcript_chunk: {e}")
            return None


def init_db():
    """Initializes the database by creating all tables."""
    print("Initializing database...")
    Base.metadata.create_all(bind=engine)
    print("Database initialized.")
