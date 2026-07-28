"""The Neon connection string is the single most fragile piece of setup:
asyncpg rejects the exact URL the Neon console hands you.
"""

from app.database import _engine_kwargs, normalize_db_url

NEON = (
    "postgresql://evalgate_owner:secret@ep-cool-bird-123.us-east-2.aws.neon.tech"
    "/neondb?sslmode=require&channel_binding=require"
)
POOLED = (
    "postgresql://evalgate_owner:secret@ep-cool-bird-123-pooler.c-4.us-east-2"
    ".aws.neon.tech/neondb?sslmode=require"
)


def test_neon_url_gets_async_driver_and_loses_libpq_params():
    url, connect_args = normalize_db_url(NEON)

    assert url.startswith("postgresql+asyncpg://")
    # Left in the URL, SQLAlchemy forwards these to asyncpg.connect() as
    # keyword arguments and the connection dies with a TypeError.
    assert "sslmode" not in url
    assert "channel_binding" not in url
    assert connect_args["ssl"] == "require"


def test_credentials_and_host_survive_normalization():
    url, _ = normalize_db_url(NEON)

    assert "evalgate_owner:secret" in url
    assert "ep-cool-bird-123.us-east-2.aws.neon.tech" in url
    assert url.endswith("/neondb")


def test_bare_postgres_scheme_is_upgraded():
    url, _ = normalize_db_url("postgres://u:p@localhost:5432/db")
    assert url.startswith("postgresql+asyncpg://")


def test_neon_host_defaults_to_tls_when_sslmode_omitted():
    _, connect_args = normalize_db_url(
        "postgresql://u:p@ep-x.us-east-2.aws.neon.tech/neondb"
    )
    assert connect_args["ssl"] == "require"


def test_plain_local_postgres_is_left_alone():
    url, connect_args = normalize_db_url(
        "postgresql+asyncpg://evalgate:evalgate@localhost:5432/evalgate"
    )
    assert url == "postgresql+asyncpg://evalgate:evalgate@localhost:5432/evalgate"
    assert "ssl" not in connect_args


def test_pooled_endpoint_disables_prepared_statement_caching():
    # Neon's -pooler endpoint is PgBouncer in transaction mode: a prepared
    # statement made on one backend is gone on the next.
    url, connect_args = normalize_db_url(POOLED)
    kwargs = _engine_kwargs(url, connect_args)

    assert connect_args["statement_cache_size"] == 0
    assert connect_args["prepared_statement_cache_size"] == 0
    assert callable(connect_args["prepared_statement_name_func"])
    assert kwargs["connect_args"] is connect_args


def test_pgbouncer_settings_are_dbapi_args_not_engine_args():
    # create_engine() raises TypeError on these two; they are only legal
    # inside connect_args. Passing them at engine level breaks startup.
    url, connect_args = normalize_db_url(POOLED)
    kwargs = _engine_kwargs(url, connect_args)

    assert "prepared_statement_cache_size" not in kwargs
    assert "prepared_statement_name_func" not in kwargs


def test_direct_endpoint_keeps_its_statement_cache():
    url, connect_args = normalize_db_url(NEON)
    _engine_kwargs(url, connect_args)

    # No PgBouncer in the path, so the cache is a straight win.
    assert "statement_cache_size" not in connect_args


def test_sqlite_url_passes_through_untouched():
    url, connect_args = normalize_db_url("sqlite+aiosqlite:///./evalgate.db")
    assert url == "sqlite+aiosqlite:///./evalgate.db"
    assert connect_args == {}
