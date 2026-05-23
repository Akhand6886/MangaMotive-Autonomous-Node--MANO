"""
Database Engine and Session Configuration.

Manages SQLAlchemy engine creation, session factory, and FastAPI dependency
injection for database sessions. Automatically creates the data directory
for SQLite databases.
"""

import os
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from config import settings

# Ensure data directory exists for SQLite database
if settings.database_url.startswith("sqlite:///"):
    db_path = settings.database_url.replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

# Create SQLAlchemy Engine with appropriate settings
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=(settings.log_level == "DEBUG"),
    pool_pre_ping=True,  # Validates connections before checkout (handles stale connections)
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Declarative Base for ORM models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session.
    Ensures the session is closed after request completion.

    Yields:
        SQLAlchemy Session instance.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

