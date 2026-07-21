"""DEPRECATED — migrations are now managed by Alembic.

This file used to be a hand-rolled `sqlite3` script that ran DDL at import time.
It only worked on SQLite (production is Postgres), defined `merchant_rules` a
second time (incompletely), and had no versioning or rollback.

Use Alembic instead (see backend/alembic/ and the db-migration skill):

    # against LOCAL sqlite — never point at the production DATABASE_URL
    DATABASE_URL="sqlite:///./financeai.db" alembic upgrade head
    alembic revision --autogenerate -m "describe change"
    alembic downgrade -1

Running this module now does nothing but print this message.
"""

if __name__ == "__main__":
    print(__doc__)
