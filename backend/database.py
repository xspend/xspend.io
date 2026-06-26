import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Read DATABASE_URL from env (production = Postgres/Neon). Fall back to local
# SQLite for development when the env var is not set.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./financeai.db")

# check_same_thread is a SQLite-only arg; only pass it when actually on SQLite.
_connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=_connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Auto-create credit_offsets table if missing
def ensure_tables(engine):
    import sqlalchemy as _sa
    with engine.connect() as conn:
        conn.execute(_sa.text('''
            CREATE TABLE IF NOT EXISTS credit_offsets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                credit_transaction_id TEXT NOT NULL,
                matched_expense_id TEXT,
                matched_category VARCHAR(100),
                credit_type VARCHAR(50),
                eligible_for_matching INTEGER DEFAULT 1,
                applied_amount DECIMAL(12,2) NOT NULL,
                unapplied_amount DECIMAL(12,2),
                match_confidence VARCHAR(20),
                match_method VARCHAR(50),
                statement_period VARCHAR(7),
                is_active INTEGER DEFAULT 1,
                matched_by VARCHAR(20) DEFAULT "system",
                created_at TEXT,
                updated_at TEXT
            )
        '''))
        conn.commit()

ensure_tables(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
