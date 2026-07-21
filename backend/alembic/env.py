import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool

from alembic import context

# Make the backend package importable so we can pull in the app's engine/models.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load backend/.env so `alembic ...` alone works the same as `uvicorn main:app`,
# without needing DATABASE_URL passed on the command line every time. An
# explicitly-exported DATABASE_URL in the shell still wins (load_dotenv doesn't
# override existing env vars).
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from app.db import engine, Base  # noqa: E402
import app.models  # noqa: E402,F401  (registers every model on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Single source of truth for the schema.
target_metadata = Base.metadata

# SQLite (local/test) can't ALTER/DROP columns in place; batch mode makes Alembic
# do the copy-and-swap there while emitting native DDL on Postgres (production).
_render_as_batch = engine.dialect.name == "sqlite"


def run_migrations_offline() -> None:
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_render_as_batch,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Reuse the app engine so DATABASE_URL (and dialect) always match the app.
    connectable = engine
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=_render_as_batch,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
