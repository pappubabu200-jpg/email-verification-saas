from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import settings

# note: for sqlite, use connect_args
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


def init_db():
    """
    Create DB tables from models. Call at startup.
    """
    try:
        Base.metadata.create_all(bind=engine)
    except SQLAlchemyError as e:
        # in production, log this (Sentry/structured logging)
        print("Error initializing DB:", e)
