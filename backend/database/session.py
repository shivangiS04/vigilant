"""
DB session factory. Defaults to SQLite for local dev (zero setup).
Set DATABASE_URL in .env to switch to Postgres for production.

  SQLite (default):   sqlite:///./vigilant.db
  Postgres:           postgresql://postgres:vigilant@localhost:5432/vigilant
"""

import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from dotenv import load_dotenv

from backend.database.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL") or "sqlite:///./vigilant.db"

# SQLite needs check_same_thread=False; ignored by other dialects
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)
    _make_event_confidence_nullable()


def _make_event_confidence_nullable(database_engine=engine):
    if "ring_events" not in inspect(database_engine).get_table_names():
        return

    if database_engine.dialect.name == "postgresql":
        with database_engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE ring_events ALTER COLUMN confidence DROP NOT NULL")
            )
        return

    if database_engine.dialect.name != "sqlite":
        raise RuntimeError("Ring event migration supports SQLite and PostgreSQL only")

    with database_engine.connect() as connection:
        columns = connection.exec_driver_sql("PRAGMA table_info(ring_events)").fetchall()
    confidence = next((column for column in columns if column[1] == "confidence"), None)
    if confidence is None or not confidence[3]:
        return

    raw_connection = database_engine.raw_connection()
    cursor = raw_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN")
        cursor.execute(
            "CREATE TABLE ring_events_migration ("
            "id VARCHAR NOT NULL PRIMARY KEY, "
            "home_id VARCHAR NOT NULL REFERENCES homes(id), "
            "camera_id VARCHAR NOT NULL REFERENCES cameras(id), "
            "type VARCHAR NOT NULL, confidence FLOAT, timestamp DATETIME NOT NULL, "
            "raw_payload JSON, created_at DATETIME)"
        )
        cursor.execute(
            "INSERT INTO ring_events_migration "
            "(id, home_id, camera_id, type, confidence, timestamp, raw_payload, created_at) "
            "SELECT id, home_id, camera_id, type, confidence, timestamp, raw_payload, created_at "
            "FROM ring_events"
        )
        cursor.execute("DROP TABLE ring_events")
        cursor.execute("ALTER TABLE ring_events_migration RENAME TO ring_events")
        cursor.execute(
            "CREATE INDEX ix_ring_events_timestamp ON ring_events (timestamp)"
        )
        cursor.execute(
            "CREATE INDEX ix_ring_events_home_timestamp ON ring_events (home_id, timestamp)"
        )
        raw_connection.commit()
    except Exception:
        raw_connection.rollback()
        raise
    finally:
        cursor.close()
        raw_connection.close()


@contextmanager
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
