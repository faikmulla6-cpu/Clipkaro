from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
database_url = os.environ.get("DATABASE_URL", "").strip()
if not database_url:
    raise RuntimeError("DATABASE_URL is required for PostgreSQL migrations.")

# Runtime traffic stays on asyncpg. Alembic deliberately uses psycopg2 because
# the baseline revision contains PostgreSQL functions/triggers in one SQL script;
# psycopg2 sends parameterless migration SQL through PostgreSQL's simple-query
# path instead of asyncpg's single prepared-statement path.
sync_url = database_url
if sync_url.startswith("postgresql+asyncpg://"):
    sync_url = "postgresql+psycopg2://" + sync_url.removeprefix("postgresql+asyncpg://")
elif sync_url.startswith("postgresql://"):
    sync_url = "postgresql+psycopg2://" + sync_url.removeprefix("postgresql://")
elif sync_url.startswith("postgres://"):
    sync_url = "postgresql+psycopg2://" + sync_url.removeprefix("postgres://")
config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
