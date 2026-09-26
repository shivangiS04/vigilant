"""
DB session factory. Defaults to SQLite for local dev (zero setup).
Set DATABASE_URL in .env to switch to Postgres for production.

  SQLite (default):   sqlite:///./vigilant.db
  Postgres:           postgresql://postgres:vigilant@localhost:5432/vigilant
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from dotenv import load_dotenv

from backend.database.models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./vigilant.db")

# SQLite needs check_same_thread=False; ignored by other dialects
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


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
