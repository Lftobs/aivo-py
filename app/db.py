from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ARRAY
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv



Base = declarative_base()

load_dotenv()

DATABASE_URL = os.getenv("DB_URL")

if not DATABASE_URL:
    raise ValueError("DB_URL environment variable is not set")

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
    recording_id = Column(String, nullable=False)
    summary_text = Column(String, nullable=False)
    actual_text = Column(String, nullable=False)
    overview = Column(String, nullable=False)
    keywords = Column(ARRAY(String), nullable=True) 
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



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

def save_summary_to_db(recording_id: int, actual_text: str, start_time: datetime, end_time: datetime, summary_text: str, overview: str, keywords: list = None):
    """Save a summary to the database."""
    db = SessionLocal()
    try:
        db_summary = Summary(
            recording_id=recording_id,
            summary_text=summary_text,
            actual_text=actual_text,
            start_time=start_time,
            end_time=end_time,
            overview=overview,
            keywords=keywords
        )
        db.add(db_summary)
        db.commit()
        db.refresh(db_summary)
        print(f"✅ Summary saved to DB with ID: {db_summary.id} (Recording ID: {recording_id})")
        return db_summary
    except Exception as e:
        db.rollback()
        print(f"❌ Error saving summary to DB: {e}")
        return None
    finally:
        db.close()