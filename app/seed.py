import os
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import get_settings

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def get_seed_session():
    settings = get_settings()

    engine = create_engine(
        url=settings.DATABASE_URL_psycopg,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=36005
    )

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()


def seed_database():
    print("Заполнение базы данных тестовыми данными...")

    current_dir = Path(__file__).parent
    init_sql_path = current_dir / "init.sql"

    if not init_sql_path.exists():
        print(f"Файл {init_sql_path} не найден!")
        return False

    try:
        with open(init_sql_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        sql_commands = sql_content.split(';')

        session = get_seed_session()
        try:
            for command in sql_commands:
                command = command.strip()
                if command:
                    try:
                        session.execute(text(command))
                        session.commit()
                    except Exception as e:
                        print(
                            f"Ошибка при выполнении команды: {command[:50]}...")
                        print(f"Ошибка: {e}")
                        session.rollback()
        finally:
            session.close()

        print("База данных успешно заполнена тестовыми данными")
        return True

    except Exception as e:
        print(f"Ошибка при заполнении базы данных тестовыми данными: {e}")
        return False
