from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings
from seed import seed_database


def get_database_engine():
    settings = get_settings()
    return create_engine(
        url=settings.DATABASE_URL_psycopg,
        echo=settings.DEBUG,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


engine = get_database_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db(drop_all: bool = False) -> None:
    from models.base import Base
    from models.user import User, Role
    from models.finance import Balance, Transaction
    from models.forecast import ForecastJob, ForecastResult

    if drop_all:
        Base.metadata.drop_all(engine)

    Base.metadata.create_all(engine)
    seed_database()


def health_check_db() -> str:
    try:
        session = SessionLocal()
        try:
            session.execute(text("SELECT 1"))
            return "connected"
        finally:
            session.close()
    except Exception as e:
        return f"disconnected: {e}"
