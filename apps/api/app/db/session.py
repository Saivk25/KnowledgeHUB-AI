"""
Decision: PostgreSQL in production/Docker, SQLite fallback for zero-setup
local development and tests.
Why: PostgreSQL gives real relational integrity and matches the frozen
schema's UUID/foreign-key design; SQLite lets contributors and CI run the
test suite with no external services.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
