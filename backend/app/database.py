from __future__ import annotations

import uuid
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


_ASYNCPG = "postgresql+asyncpg://"

# The libpq vocabulary Neon uses in its connection strings. asyncpg understands
# these values, but only as a connect_args entry named `ssl`.
_SSL_MODES = {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}


def normalize_db_url(raw: str) -> tuple[str, dict]:
    """Split a connection string into an asyncpg-safe URL plus connect_args.

    Accepts what the Neon console hands you verbatim. SQLAlchemy forwards
    unrecognised query params straight to ``asyncpg.connect()`` as keyword
    arguments, where ``sslmode`` and ``channel_binding`` raise TypeError, so
    they have to be lifted out of the URL rather than left in it.
    """
    url = raw.strip()

    # Neon (and Heroku, and psql) hand out driverless URLs; the async engine
    # needs an explicit async driver.
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            url = _ASYNCPG + url[len(prefix) :]
            break

    if not url.startswith(_ASYNCPG):
        # sqlite+aiosqlite and friends need no rewriting.
        return url, {}

    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query))
    connect_args: dict = {}

    sslmode = params.pop("sslmode", None)
    if sslmode in _SSL_MODES:
        connect_args["ssl"] = sslmode
    elif ".neon.tech" in (parts.hostname or ""):
        # Neon refuses plaintext connections; default to TLS if unspecified.
        connect_args["ssl"] = "require"

    # A SCRAM detail asyncpg does not expose. Dropping it does not weaken the
    # connection — TLS is still enforced by sslmode above.
    params.pop("channel_binding", None)

    url = urlunsplit(parts._replace(query=urlencode(params)))
    return url, connect_args


def _engine_kwargs(url: str, connect_args: dict) -> dict:
    kwargs: dict = {"echo": False, "future": True, "connect_args": connect_args}

    if not url.startswith(_ASYNCPG):
        return kwargs

    # Neon scales to zero, so a pooled connection is often already dead by the
    # time we reuse it. Pre-ping trades one round trip for not surfacing that
    # as a 500 on the first request after an idle period.
    kwargs["pool_pre_ping"] = True
    kwargs["pool_recycle"] = 300

    host = urlsplit(url).hostname or ""
    if "pooler" in host or "pgbouncer" in host:
        # PgBouncer in transaction mode hands each transaction a different
        # backend, so a prepared statement created on one is missing on the
        # next and asyncpg raises InvalidSQLStatementNameError. Disable both
        # caches and make what names remain collision-proof across backends.
        #
        # All three are DBAPI arguments in SQLAlchemy's asyncpg adapter rather
        # than create_engine() arguments, so they travel in connect_args.
        connect_args["statement_cache_size"] = 0  # asyncpg's own cache
        connect_args["prepared_statement_cache_size"] = 0  # SQLAlchemy's cache
        connect_args["prepared_statement_name_func"] = (
            lambda: f"__asyncpg_{uuid.uuid4()}__"
        )

    return kwargs


DATABASE_URL, _CONNECT_ARGS = normalize_db_url(settings.database_url)

engine = create_async_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL, _CONNECT_ARGS))
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
