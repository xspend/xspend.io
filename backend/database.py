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

# Auto-create credit_offsets table if missing. Dialect-aware so it works on
# both SQLite (local dev) and Postgres (production/Neon).
def ensure_tables(engine):
    import sqlalchemy as _sa
    is_pg = engine.dialect.name == "postgresql"
    pk = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    ddl = f'''
        CREATE TABLE IF NOT EXISTS credit_offsets (
            id {pk},
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
            matched_by VARCHAR(20) DEFAULT 'system',
            created_at TEXT,
            updated_at TEXT
        )
    '''
    # merchant_rules: user-correction learning table. Not a SQLAlchemy model,
    # so create_all won't make it — create here, dialect-aware (PG-safe).
    mr_ddl = f'''
        CREATE TABLE IF NOT EXISTS merchant_rules (
            id {pk},
            merchant_keyword TEXT NOT NULL,
            is_fixed INTEGER NOT NULL,
            user_confirmed INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            user_id TEXT,
            match_field TEXT DEFAULT 'merchant',
            match_value TEXT,
            match_type TEXT DEFAULT 'contains',
            transaction_type TEXT,
            category TEXT,
            priority INTEGER DEFAULT 0,
            source TEXT DEFAULT 'system_default',
            confidence_override REAL,
            is_active INTEGER DEFAULT 1,
            updated_at TEXT
        )
    '''
    with engine.connect() as conn:
        conn.execute(_sa.text(ddl))
        conn.execute(_sa.text(mr_ddl))
        conn.commit()

ensure_tables(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
