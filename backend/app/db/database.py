from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# DATABASE_URL must be set explicitly — there is no default. A silent fallback
# here used to mean "local" and "production" were decided by whether something
# happened to load .env first, not by what you actually typed. Same DB every
# time you forget to set it is worse than just telling you it's not set.
SQLALCHEMY_DATABASE_URL = settings.database_url

# check_same_thread is a SQLite-only arg; only pass it when actually on SQLite.
_connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

_pool_kwargs = {} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=_connect_args, **_pool_kwargs
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# NOTE: `credit_offsets` and `merchant_rules` used to be created here via raw
# `CREATE TABLE` DDL (and merchant_rules was ALSO defined, incompletely, in
# migrate.py). They are now proper SQLAlchemy models (see models.py:
# CreditOffset, MerchantRule) — a single source of truth. Schema is created by
# `Base.metadata.create_all` for fresh dev/test DBs and managed by Alembic for
# production. Do not reintroduce raw DDL here.

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
