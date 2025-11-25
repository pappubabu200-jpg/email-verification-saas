# backend/app/db.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import settings

# ---------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------
from prometheus_client import Counter, Histogram

DB_QUERY_LATENCY = Histogram(
    "db_query_latency_seconds",
    "Latency of DB queries (commit/query/rollback)"
)

DB_COMMIT_TOTAL = Counter(
    "db_commit_total",
    "Total DB commit operations",
    ["result"]  # ok | failed
)

DB_ROLLBACK_TOTAL = Counter(
    "db_rollback_total",
    "Total DB rollback operations",
    ["result"]  # ok | failed
)

DB_CONNECTION_TOTAL = Counter(
    "db_connection_total",
    "Total DB engine connection attempts",
    ["result"]  # ok | failed
)

DB_INIT_FAILURE_TOTAL = Counter(
    "db_init_failure_total",
    "DB initialization failures"
)

# ---------------------------------------------------------
# DATABASE ENGINE INIT
# ---------------------------------------------------------
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

try:
    with DB_QUERY_LATENCY.time():
        engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, future=True)
        DB_CONNECTION_TOTAL.labels(result="ok").inc()
except Exception:
    DB_CONNECTION_TOTAL.labels(result="failed").inc()
    raise

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
Base = declarative_base()


# ---------------------------------------------------------
# DB INIT FUNCTION
# ---------------------------------------------------------
def init_db():
    """
    Create DB tables from models. Call at startup.
    """
    try:
        with DB_QUERY_LATENCY.time():
            Base.metadata.create_all(bind=engine)
        DB_CONNECTION_TOTAL.labels(result="ok").inc()
    except SQLAlchemyError as e:
        DB_INIT_FAILURE_TOTAL.inc()
        print("Error initializing DB:", e)


# ---------------------------------------------------------
# SAFE HELPERS FOR COMMIT & ROLLBACK
# ---------------------------------------------------------
def safe_commit(db):
    """
    Commit with metrics instrumentation.
    """
    with DB_QUERY_LATENCY.time():
        try:
            db.commit()
            DB_COMMIT_TOTAL.labels(result="ok").inc()
        except Exception:
            DB_COMMIT_TOTAL.labels(result="failed").inc()
            raise


def safe_rollback(db):
    """
    Rollback with instrumentation.
    """
    with DB_QUERY_LATENCY.time():
        try:
            db.rollback()
            DB_ROLLBACK_TOTAL.labels(result="ok").inc()
        except Exception:
            DB_ROLLBACK_TOTAL.labels(result="failed").inc()
            raise


# OPTIONAL: You can wrap queries using safe_query if needed:
def safe_query(fn, *args, **kwargs):
    """
    Wrap any DB operation/query with latency tracking.
    """
    with DB_QUERY_LATENCY.time():
        return fn(*args, **kwargs)
