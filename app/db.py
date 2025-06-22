from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv


Base = declarative_base()

load_dotenv()

DATABASE_URL = os.getenv("DB_URL")

engine = create_engine(DATABASE_URL)

class Recording(Base):
    """Database model for audio recordings."""
    __tablename__ = "recordings"

    id = Column(Integer, primary_key=True, index=True)
    unique_id = Column(String, unique=False, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    transcript = Column(String, nullable=True)

    class Summary(Base):
        """Database model for recording summaries."""
        __tablename__ = "summaries"

        id = Column(Integer, primary_key=True, index=True)
        recording_id = Column(Integer, nullable=False)
        summary_text = Column(String, nullable=False)
        created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Add mock data
db = SessionLocal()


def save_recording_to_db(unique_id: str, start_time: datetime, end_time: datetime, transcript: str):
    """Save a recording to the database."""
    db = SessionLocal()
    try:
        db_recording = Recording(
            unique_id=unique_id,
            start_time=start_time,
            end_time=end_time,
            transcript=transcript
        )
        db.add(db_recording)
        db.commit()
        db.refresh(db_recording)
        print(f"✅ Recording saved to DB with ID: {db_recording.id} (UUID: {unique_id})")
        return db_recording
    except Exception as e:
        db.rollback()
        print(f"❌ Error saving recording to DB: {e}")
        return None
    finally:
        db.close()
