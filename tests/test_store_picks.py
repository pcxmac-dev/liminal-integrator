"""A store's pick naming an instance in the integrator (1.16.0; liminal-libs 1.91.0 stores.py, Monday list item 10): the
fetcher's app holds the database plugins with its login and its database's folder, a pick naming an instance writes
through that plugin's `open` in this process and nowhere else, a bare pick is as before, and the fetcher's end closes
what it kept open. A stand-in plugin and a stand-in server (an in-memory SQLite database): no server, no process, no
port."""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import replace

import pytest

from liminal_integrator import fetcher, lib
from liminal_libs import stores
from liminal_libs.sources import registry
from liminal_libs.storage.databases import DatabasePlugin, variable_of


class Conn:
    """A stand-in PostgreSQL connection: its statements run on an in-memory SQLite database (format marks as qmarks)."""

    def __init__(self, server):
        self.server, self.closed = server, False

    def cursor(self):
        conn = self

        class Cursor:
            rows: list = []

            def execute(self, sql, args=()):
                assert not conn.closed
                self.rows = conn.server["db"].execute(sql.replace("%s", "?"), list(args)).fetchall()

            def executemany(self, sql, rows):
                assert not conn.closed
                conn.server["db"].executemany(sql.replace("%s", "?"), [list(r) for r in rows])

            def fetchone(self):
                return self.rows[0] if self.rows else None

            def fetchall(self):
                return list(self.rows)

        return Cursor()

    def commit(self):
        self.server["db"].commit()

    def rollback(self):
        self.server["db"].rollback()

    def close(self):
        self.closed = True


class PostgresStandIn(DatabasePlugin):
    name, title, ENGINE, api = "postgres", "PostgreSQL", "postgres", "2.3"
    options = (variable_of("postgres"),)
    METHODS, HOLDS, SERVER = ("tcp",), ("documents",), True

    def builtin(self, data_dir):
        return ()

    def open(self, instance, part="", read_only=True, data_dir=None):
        conn = Conn(self.server)
        self.server["opened"].append((instance.name, read_only, conn))
        return conn


@pytest.fixture
def settings(tmp_path):
    return replace(lib.config.load_settings(env={}, env_file=None), db_path=tmp_path / "liminal.db")


@pytest.fixture
def held(settings, monkeypatch):
    """The fetcher with the stand-in PostgreSQL plugin found by the registry and attached by its app (its login holding
    the instance `main`); the plugins `massive` keeping documents."""
    login = lib.EnvironmentLogin(env={"POSTGRES_INSTANCES": json.dumps({"v": 1, "instances": [
        {"name": "main", "title": "Main documents", "where": "127.0.0.1", "method": "tcp", "port": 5432,
         "database": "liminal_docs", "holds": ["documents"]}]})})
    plugin = PostgresStandIn()
    plugin.__dict__["server"] = {"db": sqlite3.connect(":memory:", check_same_thread=False), "opened": []}
    monkeypatch.setattr(registry, "databases", lambda: {"postgres": plugin})
    monkeypatch.setattr(registry, "database", lambda name: plugin if name == "postgres" else None)
    monkeypatch.setattr(stores, "plugin_types", lambda name: ["documents"] if name == "massive" else [])
    monkeypatch.setattr(lib, "history_due", lambda s: False)
    stores.forget_instances()
    stores.close_instances()
    f = fetcher.Fetcher(settings, lambda *_: None, login=login)
    f.by_event = False
    attached = f.app.attach_needs()
    yield f, plugin, attached
    plugin.detach()
    stores.close_instances()
    stores.forget_instances()


def headline(i, t):
    return {"id": str(i), "published_ms": t, "title": f"h{i}", "publisher": "P", "url": None, "tickers": ["AAPL"]}


def test_the_fetchers_app_holds_the_plugins_with_its_login_and_its_folder(held, settings):
    f, plugin, attached = held
    assert attached == ["postgres"] and plugin.app is f.app and plugin.login is f.app.login
    assert f.app.db_path == settings.db_path and plugin.data_dir() == settings.db_path.parent
    assert stores.database_plugin("postgres") is plugin  # attached here: the app's, not a lent copy
    assert [c["name"] for c in stores.instance_choices("documents", settings.db_path.parent)] == ["postgres:main"]


def test_a_pick_naming_an_instance_writes_there_and_the_fetchers_end_closes_it(held, settings):
    f, plugin, _ = held
    with lib.Store(settings.db_path, check_same_thread=False) as store:
        store.save_news("massive", [headline(1, 1000)])
        stores.pick(store, "massive", "documents", "postgres:main")
        assert store.save_news("massive", [headline(2, 2000), headline(3, 3000)]) == 2
        assert store.conn.execute("SELECT COUNT(*) FROM news").fetchone()[0] == 1  # nothing new here, nothing moved
        rows = plugin.server["db"].execute("SELECT id FROM liminal_news ORDER BY id").fetchall()
        assert [r[0] for r in rows] == ["2", "3"]
        assert [n["id"] for n in store.news("massive")] == ["3", "2", "1"]
    opened = plugin.server["opened"]
    assert [(name, ro) for name, ro, _ in opened] == [("main", False)] and not opened[0][2].closed
    stop = threading.Event()
    stop.set()
    f.run(stop=stop)
    assert opened[0][2].closed  # let go with the fetcher's store


def test_a_bare_pick_is_as_before(held, settings):
    f, plugin, _ = held
    with lib.Store(settings.db_path, check_same_thread=False) as store:
        stores.pick(store, "massive", "documents", "sqlite")
        assert store.save_news("massive", [headline(1, 1000)]) == 1
        assert store.conn.execute("SELECT COUNT(*) FROM news").fetchone()[0] == 1
        assert stores.in_effect(store, "massive", "documents") == "sqlite"
    assert plugin.server["opened"] == []  # no instance opened
