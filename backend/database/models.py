"""
SQLAlchemy ORM — works with SQLite (dev) and PostgreSQL (prod).

Tables:
  homes       — one row per home
  cameras     — cameras associated with a home
  ring_events — raw Ring events
  patterns    — MOTIF-scored sequences
  baselines   — learned normal patterns per home
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Boolean, Integer,
    DateTime, ForeignKey, Text, Index, create_engine, JSON
)
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.orm import declarative_base, relationship, Session

Base = declarative_base()


class Home(Base):
    __tablename__ = "homes"

    id = Column(String, primary_key=True)          # e.g. "home_001"
    address = Column(String, nullable=False)
    resident_count = Column(Integer, default=1)
    normal_hours_start = Column(Integer, default=7)  # 7 AM
    normal_hours_end = Column(Integer, default=23)   # 11 PM
    baseline_established_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    cameras = relationship("Camera", back_populates="home")
    events = relationship("RingEvent", back_populates="home")
    patterns = relationship("Pattern", back_populates="home")
    baselines = relationship("Baseline", back_populates="home")


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(String, primary_key=True)           # e.g. "cam_001"
    home_id = Column(String, ForeignKey("homes.id"), nullable=False)
    name = Column(String, nullable=False)           # "front_door"
    location = Column(String)                       # "Front entrance"
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    home = relationship("Home", back_populates="cameras")
    events = relationship("RingEvent", back_populates="camera")


class RingAccount(Base):
    __tablename__ = "ring_accounts"

    account_id = Column(String, primary_key=True)
    partner_user_id = Column(String, index=True)
    home_id = Column(String, ForeignKey("homes.id"))
    account_identifier = Column(String)
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=False)
    access_token_expires_at = Column(DateTime, nullable=False)
    status = Column(String, nullable=False, default="unclaimed", index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    home = relationship("Home")


class RingWebhookReceipt(Base):
    __tablename__ = "ring_webhook_receipts"

    request_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=False, index=True)
    event_id = Column(String, nullable=False)
    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime)


class RingEvent(Base):
    __tablename__ = "ring_events"

    id = Column(String, primary_key=True)
    home_id = Column(String, ForeignKey("homes.id"), nullable=False)
    camera_id = Column(String, ForeignKey("cameras.id"), nullable=False)
    type = Column(String, nullable=False)           # person_detected | motion_detected | …
    confidence = Column(Float, nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    raw_payload = Column(JSON)                      # original Ring event JSON
    created_at = Column(DateTime, default=datetime.utcnow)

    home = relationship("Home", back_populates="events")
    camera = relationship("Camera", back_populates="events")

    __table_args__ = (
        Index("ix_ring_events_home_timestamp", "home_id", "timestamp"),
    )


class Pattern(Base):
    __tablename__ = "patterns"

    id = Column(String, primary_key=True)
    home_id = Column(String, ForeignKey("homes.id"), nullable=False)
    pattern_type = Column(String, nullable=False)   # rapid_return | unusual_entrance | …
    fingerprint = Column(String)                    # MOTIF fingerprint hash
    event_ids = Column(JSON)                        # ordered list of ring_event IDs
    novelty_score = Column(Float)
    adaptation_score = Column(Float)
    temporal_weight = Column(Float)
    competition_score = Column(Float)
    salience_score = Column(Float, index=True)
    flagged = Column(Boolean, default=False)
    explanation = Column(Text)                      # Bedrock-generated text
    detected_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    home = relationship("Home", back_populates="patterns")

    __table_args__ = (
        Index("ix_patterns_home_detected", "home_id", "detected_at"),
        Index("ix_patterns_flagged", "flagged", "salience_score"),
    )


class Baseline(Base):
    __tablename__ = "baselines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    home_id = Column(String, ForeignKey("homes.id"), nullable=False)
    fingerprint = Column(String, nullable=False)
    pattern_type = Column(String)
    occurrence_count = Column(Integer, default=1)
    first_seen = Column(DateTime)
    last_seen = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    home = relationship("Home", back_populates="baselines")

    __table_args__ = (
        Index("ix_baselines_home_fingerprint", "home_id", "fingerprint", unique=True),
    )


# ------------------------------------------------------------------
# DB setup helper
# ------------------------------------------------------------------

def create_tables(database_url: str):
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


if __name__ == "__main__":
    # local dev: docker run -e POSTGRES_PASSWORD=vigilant -p 5432:5432 postgres
    url = "postgresql://postgres:vigilant@localhost:5432/vigilant"
    engine = create_tables(url)
    print("Tables created:", list(Base.metadata.tables.keys()))
