from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import get_settings


def get_database_engine():
    settings = get_settings()
    return create_engine(
        url=settings.DATABASE_URL_psycopg,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


engine = get_database_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
