"""
Database Engine and Session Configuration (Asynchronous).

Manages async SQLAlchemy engine creation, session factory, and FastAPI dependency
injection for database sessions. Automatically creates the data directory
for SQLite databases.
"""

import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from config import settings

# Ensure data directory exists for SQLite database
db_url = settings.database_url
if db_url.startswith("sqlite+aiosqlite:///"):
    db_path = db_url.replace("sqlite+aiosqlite:///", "")
elif db_url.startswith("sqlite:///"):
    db_path = db_url.replace("sqlite:///", "")
else:
    db_path = ""

if db_path:
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

# Create Async SQLAlchemy Engine
engine = create_async_engine(
    settings.database_url,
    echo=(settings.log_level == "DEBUG"),
)

# Create AsyncSessionLocal factory
SessionLocal = async_sessionmaker(
    autocommit=False, 
    autoflush=False, 
    class_=AsyncSession, 
    bind=engine,
    expire_on_commit=False
)

# Declarative Base for ORM models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an asynchronous database session.
    Ensures the session is closed after request completion.

    Yields:
        SQLAlchemy AsyncSession instance.
    """
    async with SessionLocal() as db:
        try:
            yield db
        finally:
            await db.close()


