"""
===============================================================================
Test Data Setup / Teardown / Reset Primitives
===============================================================================

Reusable, environment-driven helpers for putting the system under test into a
known state before a test and cleaning up afterwards. Nothing here is hardcoded:
every endpoint and credential comes from the environment, and each helper is a
safe no-op / skip when its configuration is absent.

Environment Variables:
    SEED_API_BASE_URL: Base URL of the API used to create/delete test data
    SEED_API_TOKEN:    Optional bearer token for that API
    SEED_DB_DSN:       Optional database DSN (sqlite:///path.db, or a
                       postgresql:// DSN when psycopg is installed)

Fixtures (registered in conftest.py):
    cleanup          function-scoped CleanupRegistry (LIFO teardown)
    session_cleanup  session-scoped CleanupRegistry
    api_seed         ApiSeeder; entities it creates are deleted on teardown
    db_seed          DbSeeder; no-op when SEED_DB_DSN is unset

Pattern (yield setup -> teardown):
    @pytest.fixture
    def widget(api_seed):
        created = api_seed.create("/widgets", {"name": "demo"})  # auto-deleted
        yield created

Author: PMAC
===============================================================================
"""
import os
import re
import sqlite3
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import httpx
import pytest


class CleanupRegistry:
    """Tracks teardown callbacks and runs them last-in-first-out."""

    def __init__(self):
        self._actions: list[tuple[str, Callable[[], Any]]] = []

    def register(self, description: str, action: Callable[[], Any]) -> None:
        self._actions.append((description, action))

    def __len__(self) -> int:
        return len(self._actions)

    def run(self) -> list[str]:
        """Run every action even if some fail; return failure descriptions."""
        failures = []
        while self._actions:
            description, action = self._actions.pop()
            try:
                action()
            except Exception as e:  # keep cleaning; report at the end
                failures.append(f"{description}: {e}")
        return failures


class ApiSeeder:
    """Small HTTP client for creating/resetting/deleting test data."""

    def __init__(self, base_url: str, token: Optional[str] = None,
                 registry: Optional[CleanupRegistry] = None,
                 transport: Optional[httpx.BaseTransport] = None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client = httpx.Client(base_url=base_url, headers=headers,
                                    timeout=15, transport=transport)
        self._registry = registry

    @classmethod
    def from_env(cls, registry: Optional[CleanupRegistry] = None) -> Optional["ApiSeeder"]:
        base_url = os.getenv("SEED_API_BASE_URL")
        if not base_url:
            return None
        return cls(base_url, os.getenv("SEED_API_TOKEN"), registry)

    def create(self, path: str, payload: dict, id_field: str = "id",
               delete_path: Optional[str] = None) -> dict:
        """
        POST payload to path and schedule deletion on teardown.
        delete_path defaults to f"{path}/{<id_field>}".
        """
        response = self._client.post(path, json=payload)
        response.raise_for_status()
        body = response.json() if response.content else {}
        if self._registry is not None and body.get(id_field) is not None:
            target = delete_path.format(id=body[id_field]) if delete_path \
                else f"{path.rstrip('/')}/{body[id_field]}"
            self._registry.register(f"DELETE {target}", lambda: self.delete(target))
        return body

    def delete(self, path: str) -> None:
        response = self._client.delete(path)
        if response.status_code != 404:  # already gone is fine
            response.raise_for_status()

    def reset(self, path: str) -> None:
        """Call a reset endpoint (POST) to restore baseline data."""
        self._client.post(path).raise_for_status()

    def close(self) -> None:
        self._client.close()


_SQL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class DbSeeder:
    """
    Seed/reset a database via DB-API. ``enabled`` is False when no DSN is set,
    and every method is then a no-op, so tests can use it unconditionally.
    """

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn
        self._conn = None

    @property
    def enabled(self) -> bool:
        return bool(self.dsn)

    def _connect(self):
        if self._conn is None:
            parsed = urlparse(self.dsn)
            if parsed.scheme == "sqlite":
                path = self.dsn.split("sqlite:///", 1)[-1] or ":memory:"
                self._conn = sqlite3.connect(path)
            elif parsed.scheme in ("postgres", "postgresql"):
                try:
                    import psycopg
                except ImportError:
                    pytest.skip("SEED_DB_DSN is postgres but psycopg is not installed")
                self._conn = psycopg.connect(self.dsn)
            else:
                raise ValueError(f"Unsupported SEED_DB_DSN scheme: {parsed.scheme!r}")
        return self._conn

    def execute(self, sql: str, params: tuple = ()) -> list:
        """Run one statement, commit, and return any rows."""
        if not self.enabled:
            return []
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else []
        conn.commit()
        return rows

    def run_script(self, sql: str) -> None:
        """Run a multi-statement setup script (sqlite) or file contents."""
        if not self.enabled:
            return
        conn = self._connect()
        if isinstance(conn, sqlite3.Connection):
            conn.executescript(sql)
        else:
            for statement in filter(None, (s.strip() for s in sql.split(";"))):
                conn.cursor().execute(statement)
            conn.commit()

    def reset(self, *tables: str) -> None:
        """Delete all rows from the given tables (names validated)."""
        for table in tables:
            if not _SQL_NAME.match(table):
                raise ValueError(f"Invalid table name: {table!r}")
            self.execute(f"DELETE FROM {table}")  # noqa: S608 - name validated

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

def _drain(registry: CleanupRegistry) -> None:
    failures = registry.run()
    if failures:
        pytest.fail("Teardown cleanup failed:\n  " + "\n  ".join(failures),
                    pytrace=False)


@pytest.fixture
def cleanup():
    """Register callbacks with cleanup.register(desc, fn); run LIFO after the test."""
    registry = CleanupRegistry()
    yield registry
    _drain(registry)


@pytest.fixture(scope="session")
def session_cleanup():
    """Like `cleanup`, but for shared data torn down once at session end."""
    registry = CleanupRegistry()
    yield registry
    _drain(registry)


@pytest.fixture
def api_seed(cleanup):
    """ApiSeeder from env; skips the test when SEED_API_BASE_URL is unset."""
    seeder = ApiSeeder.from_env(cleanup)
    if seeder is None:
        pytest.skip("SEED_API_BASE_URL not set; API seeding unavailable")
    yield seeder
    # Fixtures tear down dependents first, so drain here (before closing the
    # client) rather than leaving the deletes to `cleanup`.
    try:
        _drain(cleanup)
    finally:
        seeder.close()


@pytest.fixture
def db_seed():
    """DbSeeder from SEED_DB_DSN; every method is a no-op when unset."""
    seeder = DbSeeder(os.getenv("SEED_DB_DSN"))
    yield seeder
    seeder.close()
