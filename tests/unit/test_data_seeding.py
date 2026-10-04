"""Unit tests for utils.data_seeding (no network / external DB needed)."""
import httpx
import pytest

from utils.data_seeding import ApiSeeder, CleanupRegistry, DbSeeder


def test_cleanup_runs_lifo_and_continues_after_failure():
    order = []
    reg = CleanupRegistry()
    reg.register("a", lambda: order.append("a"))
    reg.register("boom", lambda: 1 / 0)
    reg.register("c", lambda: order.append("c"))
    failures = reg.run()
    assert order == ["c", "a"]
    assert len(failures) == 1 and failures[0].startswith("boom")
    assert len(reg) == 0


def _seeder(calls, registry):
    def handler(request):
        calls.append((request.method, request.url.path, request.headers.get("authorization")))
        if request.method == "POST":
            return httpx.Response(201, json={"id": 7})
        return httpx.Response(204)
    return ApiSeeder("http://api.test", "tok", registry, httpx.MockTransport(handler))


def test_api_create_registers_delete_and_sends_token():
    calls, reg = [], CleanupRegistry()
    seeder = _seeder(calls, reg)
    assert seeder.create("/items", {"n": 1}) == {"id": 7}
    assert calls[0] == ("POST", "/items", "Bearer tok")
    assert reg.run() == []
    assert calls[1][:2] == ("DELETE", "/items/7")


def test_api_from_env_none_without_base_url(monkeypatch):
    monkeypatch.delenv("SEED_API_BASE_URL", raising=False)
    assert ApiSeeder.from_env() is None


def test_db_seeder_noop_without_dsn():
    db = DbSeeder(None)
    assert not db.enabled
    assert db.execute("SELECT 1") == []
    db.run_script("CREATE TABLE x(a)")
    db.reset("x")


def test_db_seed_and_reset_sqlite(tmp_path):
    db = DbSeeder(f"sqlite:///{tmp_path}/t.db")
    db.run_script("CREATE TABLE users(name TEXT);")
    db.execute("INSERT INTO users VALUES (?)", ("ada",))
    assert db.execute("SELECT name FROM users") == [("ada",)]
    db.reset("users")
    assert db.execute("SELECT name FROM users") == []
    with pytest.raises(ValueError):
        db.reset("users; DROP TABLE users")
    db.close()
