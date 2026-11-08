"""The databases themselves on the integrator's page (databases.py, app.py's routes; the user, 2026-11-07:
"the integrator will have stats for the databases themselves, the platform only cares about hardware").
Every database here is a stand-in: canned connections, pages made by hand, a MongoDB client that
answers what a test says; the files a folder holds are plain bytes (conftest's no_real_databases
refuses the real openers and MongoDB's port)."""
from __future__ import annotations

import os
import re
import sqlite3
import struct
import sys
import types
from http import HTTPStatus

import pytest

from liminal_integrator import databases as dbs
from liminal_integrator import lib
from liminal_integrator.app import IntegratorApp
from liminal_integrator.databases import connect_duckdb, connect_sqlite, mongo_client, port_open  # the real ones


# -- stand-ins -----------------------------------------------------------------------------------
class Rows:
    def __init__(self, rows):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __iter__(self):
        return iter(self.rows)


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakeSqlite:
    """A SQLite connection's stand-in: canned answers by statement, every statement kept; a table in
    `slow` counts until the progress handler gives up (the clock moving while it counts)."""

    def __init__(self, schema=(), counts=None, stat1=(), pragmas=None, slow=(), clock=None, manifest=None):
        self.schema, self.counts, self.stat1, self.slow, self.clock = list(schema), dict(counts or {}), list(stat1), set(slow), clock
        self.manifest = manifest
        self.pragmas = {"page_size": 4096, "page_count": 100, "freelist_count": 2, "journal_mode": "wal", "user_version": 7}
        self.pragmas.update(pragmas or {})
        self.asked: list[str] = []
        self.handler = None
        self.closed = False

    def execute(self, sql, args=()):
        assert not self.closed, "asked after it was closed"
        self.asked.append(sql)
        if sql.startswith("PRAGMA "):
            return Rows([(self.pragmas[sql[7:]],)])
        if sql == "SELECT type, name, tbl_name, rootpage, sql FROM sqlite_master":
            return Rows(self.schema)
        if sql == "SELECT tbl, idx, stat FROM sqlite_stat1":
            return Rows(self.stat1)
        if sql == "SELECT 1 FROM sqlite_master WHERE type='table' AND name='history'":
            return Rows([(1,)] if self.manifest is not None else [])
        if sql.startswith("SELECT month, file, bars, built, bytes, archived_at, seconds, stale FROM history"):
            return Rows(self.manifest or [])
        m = re.fullmatch(r'SELECT count\(\*\) FROM "(.+)"', sql)
        if m:
            name = m.group(1)
            if name in self.slow:
                while not self.handler():
                    self.clock.t += 0.5
                raise sqlite3.OperationalError("interrupted")
            return Rows([(self.counts[name],)])
        raise AssertionError(f"not a statement this stand-in knows: {sql}")

    def set_progress_handler(self, handler, n):
        self.handler = handler

    def close(self):
        self.closed = True


def table(name, root, without_rowid=False):
    return ("table", name, name, root, f"CREATE TABLE {name} (a, b{', PRIMARY KEY (a)' if without_rowid else ''})"
                                       f"{' WITHOUT ROWID' if without_rowid else ''}")


# B-tree pages made by hand (the SQLite file format: a page's type, its cells, its children)
SIZE = 512


def interior(kind, children, first=False):
    at = 100 if first else 0
    buf = bytearray(SIZE)
    buf[at] = kind
    struct.pack_into(">H", buf, at + 3, len(children) - 1)
    struct.pack_into(">I", buf, at + 8, children[-1])
    end = SIZE
    for k, child in enumerate(children[:-1]):
        end -= 8
        struct.pack_into(">I", buf, end, child)
        struct.pack_into(">H", buf, at + 12 + 2 * k, end)
    return bytes(buf)


def leaf(kind, cells, first=False):
    at = 100 if first else 0
    buf = bytearray(SIZE)
    buf[at] = kind
    struct.pack_into(">H", buf, at + 3, cells)
    return bytes(buf)


class Pages:
    """A file's pages by number, as PageReader gives them; `asked` keeps every page read."""

    def __init__(self, pages):
        self.pages = dict(pages)
        self.asked: list[int] = []
        self.entered = self.exited = 0

    def __call__(self, path, page_size):  # what sqlite_figures calls: PageReader(path, page_size)
        return self

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *exc):
        self.exited += 1

    def page(self, n, keep=False):
        self.asked.append(n)
        if n not in self.pages:
            raise ValueError(f"page {n} is not in the file")
        return self.pages[n]


class Alternating:
    """An rng that takes each child in turn: a path's choices known in advance."""

    def __init__(self):
        self.i = 0

    def randrange(self, n):
        self.i += 1
        return (self.i - 1) % n


# -- the B-tree estimate -------------------------------------------------------------------------
def test_a_btree_estimate_counts_an_index_trees_interior_entries_and_a_table_trees_leaves_alone():
    pages = Pages({2: interior(2, [3, 4, 5, 6]), **{n: leaf(10, 10) for n in (3, 4, 5, 6)},  # index: 3 + 4 x 10
                   7: interior(5, [8, 9, 10]), **{n: leaf(13, 7) for n in (8, 9, 10)},  # table: 3 x 7
                   1: leaf(13, 5, first=True)})  # a tree at page 1: its header after the file's
    assert dbs.btree_entries(pages.page, 2, index=True) == 43.0
    assert dbs.btree_entries(pages.page, 7, index=False) == 21.0
    assert dbs.btree_entries(pages.page, 1, index=False) == 5.0
    assert dbs.btree_entries(pages.page, 2, index=False) is None  # an index tree read as a table's: no path holds
    # uneven leaves: each path's estimate is 2 x what it meets, their mean the whole (5 + 15)
    uneven = Pages({11: interior(5, [12, 13]), 12: leaf(13, 5), 13: leaf(13, 15)})
    assert dbs.btree_entries(uneven.page, 11, index=False, probes=4, rng=Alternating()) == 20.0
    assert len(uneven.asked) == 8  # 4 paths of 2 pages: never more than the paths


def test_a_btree_estimate_leaves_out_a_broken_path_and_gives_none_when_none_holds():
    torn = Pages({20: interior(5, [21, 22]), 21: leaf(13, 4), 22: leaf(10, 9)})  # 22 is another tree's page now
    assert dbs.btree_entries(torn.page, 20, index=False, probes=4, rng=Alternating()) == 8.0  # the paths through 21
    gone = Pages({30: interior(5, [31, 32])})  # its children not in the file yet (still in the -wal)
    assert dbs.btree_entries(gone.page, 30, index=False) is None
    loop = Pages({40: interior(5, [40, 40])})  # a page its own child: too deep, given up
    assert dbs.btree_entries(loop.page, 40, index=False, probes=2) is None


def test_the_page_reader_reads_pages_straight_from_the_file_and_never_past_it(tmp_path):
    f = tmp_path / "pages.bin"  # plain bytes laid out as pages: no database opened
    f.write_bytes(leaf(13, 3, first=True) + interior(5, [3, 4]) + leaf(13, 2) + leaf(13, 6))
    with dbs.PageReader(f, SIZE) as r:
        assert r.pages == 4 and r.page(2)[0] == 5 and r.page(4, keep=True)[0] == 13
        assert dbs.btree_entries(r.page, 2, index=False, probes=2, rng=Alternating()) == 8.0
        with pytest.raises(ValueError):
            r.page(5)
        with pytest.raises(ValueError):
            r.page(0)
    assert r._f is None and r._kept == {}  # closed, nothing kept


# -- a SQLite file's figures ---------------------------------------------------------------------
def test_a_small_files_tables_are_counted_outright_and_the_connection_closed():
    conn = FakeSqlite(schema=[table("bars", 2, without_rowid=True), table("kv", 3),
                              ("index", "kv_by", "kv", 4, "CREATE INDEX kv_by ON kv (b)"),
                              ("table", "search", "search", 0, "CREATE VIRTUAL TABLE search USING fts5(a)"),
                              table("sqlite_sequence", 5)],
                      counts={"bars": 12, "kv": 400})
    out = dbs.sqlite_figures("x.db", 10_000, lambda p: conn, pages=lambda *a: pytest.fail("no page read for a small file"))
    assert conn.closed and out["engine"] == "sqlite" and (out["pageSize"], out["pages"], out["freePages"]) == (4096, 100, 2)
    assert (out["journal"], out["userVersion"], out["indexes"], out["statistics"]) == ("wal", 7, 1, False)
    assert [(t["name"], t["rows"], t["how"]) for t in out["tables"]] == [("kv", 400, "counted"), ("bars", 12, "counted"),
                                                                       ("search", None, "virtual")]
    assert out["tables"][1]["withoutRowid"] and not out["tables"][0]["withoutRowid"] and out["tables"][0]["indexes"] == 1


def test_a_large_files_tables_are_never_scanned_statistics_or_their_btree_instead():
    big = dbs.EXACT_BYTES * 1000
    leaves = list(range(10, 20))
    pages = Pages({2: interior(2, [3, 4, 5]), **{n: interior(2, leaves) for n in (3, 4, 5)},  # bars: 2 + 3 x 9 + 30 x 60,000
                   **{n: leaf(10, 60_000) for n in leaves},
                   6: interior(5, [7, 8]), 7: leaf(13, 30), 8: leaf(13, 30)})  # runs: about 60, counted outright
    conn = FakeSqlite(schema=[table("bars", 2, without_rowid=True), table("quality", 5), table("runs", 6),
                              ("table", "sqlite_stat1", "sqlite_stat1", 9, "CREATE TABLE sqlite_stat1(tbl,idx,stat)")],
                      stat1=[("quality", "quality_by", "52000 3"), ("quality", None, "51000")], counts={"runs": 61})
    out = dbs.sqlite_figures("massive.db", big, lambda p: conn, pages)
    rows = {t["name"]: (t["rows"], t["how"]) for t in out["tables"]}
    assert rows == {"bars": (1_800_029, "estimated"), "quality": (52_000, "statistics"), "runs": (61, "counted")}
    assert not any('"bars"' in s or '"quality"' in s for s in conn.asked)  # never counted: the big ones
    assert out["statistics"] and conn.closed and pages.entered == pages.exited == 1


def test_counting_outright_stops_at_its_budget_and_keeps_the_estimate():
    clock = Clock(0.0)
    pages = Pages({2: leaf(13, 90)})
    conn = FakeSqlite(schema=[table("slow", 2), table("other", 9)], slow={"slow"}, clock=clock, counts={})
    out = dbs.sqlite_figures("x.db", 1000, lambda p: conn, pages, clock=clock)
    rows = {t["name"]: (t["rows"], t["how"]) for t in out["tables"]}
    assert rows["slow"] == (90, "estimated")  # its count given up: its B-tree's figure
    assert rows["other"] == (None, "unknown")  # no time left to count, its tree not in the file
    assert clock.t >= dbs.COUNT_BUDGET_S and conn.handler is None and conn.closed


def test_a_file_whose_pages_cannot_be_read_leaves_its_large_tables_uncounted():
    conn = FakeSqlite(schema=[table("bars", 2, without_rowid=True), table("bars_more", 3, without_rowid=True)])

    def in_use(path, page_size):
        raise PermissionError("in use")
    out = dbs.sqlite_figures("x.db", dbs.EXACT_BYTES + 1, lambda p: conn, in_use)
    assert [(t["name"], t["rows"], t["how"]) for t in out["tables"]] == [("bars", None, "unknown"), ("bars_more", None, "unknown")]
    assert conn.closed and not any("count(" in s for s in conn.asked)


def test_a_sqlite_file_is_opened_read_only_and_query_only(monkeypatch, tmp_path):
    seen, ran = [], []

    class Conn:
        def execute(self, sql):
            ran.append(sql)

    monkeypatch.setattr(dbs.sqlite3, "connect", lambda *a, **kw: seen.append((a, kw)) or Conn())
    connect_sqlite(tmp_path / "my data" / "x.db")
    (uri,), kw = seen[0]
    assert uri.startswith("file:///") and uri.endswith("/my%20data/x.db?mode=ro") and kw["uri"] is True
    assert ran == ["PRAGMA query_only=ON"]


def test_a_duckdb_file_is_opened_read_only_and_closed_after_its_table_statistics(monkeypatch, tmp_path):
    seen = []

    class Conn:
        closed = False

        def execute(self, sql):
            if "duckdb_tables()" in sql:
                assert "NOT internal" in sql
                return Rows([("main", "bars", 5000, 13, 0), ("main", "about", 1, 6, 0), ("aux", "notes", None, 2, 1)])
            return Rows([("v2.0.0",)])

        def close(self):
            Conn.closed = True

    fake = types.ModuleType("duckdb")
    fake.connect = lambda path, **kw: seen.append((path, kw)) or Conn()
    monkeypatch.setitem(sys.modules, "duckdb", fake)
    out = dbs.duckdb_figures(tmp_path / "x.duckdb", connect_duckdb)
    assert seen[0][1]["read_only"] is True and Conn.closed
    assert [(t["name"], t["rows"]) for t in out["tables"]] == [("bars", 5000), ("about", 1), ("aux.notes", None)]
    assert out["duckdb"] == "v2.0.0" and all(t["how"] == "statistics" for t in out["tables"])


# -- a feed's months in DuckDB: the manifest, no month file opened -------------------------------
def test_a_feeds_months_come_from_its_manifest_against_the_files_on_disk(tmp_path):
    feed_db = tmp_path / "a.db"
    feed_db.write_bytes(b"stand-in")
    conn = FakeSqlite(manifest=[("2026-01", "2026-01.2.duckdb", 1000, 10, 300, 1_767_225_600_000, 2.5, 0),
                                ("2026-02", "2026-02.1.duckdb", 2000, 0, 400, 1_769_904_000_000, 3.0, 1),
                                ("2026-03", "2026-03.1.duckdb", 5, 0, 9, 1_772_323_200_000, 0.1, 0)])
    files = [("2026-01.1.duckdb", 280, 1.0), ("2026-01.2.duckdb", 300, 2.0), ("2026-01.2.duckdb.wal", 4, 2.0),
             ("2026-02.1.duckdb", 400, 3.0), ("2026-04.1.duckdb.part", 50, 4.0)]
    out = dbs.history_figures(feed_db, files, lambda p: conn)
    assert conn.closed and out["manifest"] == "a.db" and [m["month"] for m in out["months"]] == ["2026-03", "2026-02", "2026-01"]
    assert (out["bars"], out["built"], out["stale"], out["missing"]) == (3005, 10, 1, 1)  # 2026-03's file is not there
    assert [(t["name"], t["rows"], t["how"]) for t in out["tables"]] == [("bars", 3005, "manifest"), ("built_bars", 10, "manifest")]
    assert {u["file"]: u["state"] for u in out["unlisted"]} == {"2026-01.1.duckdb": "superseded", "2026-04.1.duckdb.part": "copying"}
    assert out["months"][2]["copiedAt"] == "2026-01-01T00:00:00+00:00" and out["months"][1]["stale"] is True
    assert dbs.history_figures(None, files[:1], lambda p: pytest.fail("no feed file: nothing to open"))["unlisted"][0]["state"] == "unlisted"


# -- MongoDB: asked only while it runs -----------------------------------------------------------
class FakeColl:
    def __init__(self, stats, fails=False):
        self.stats, self.fails = stats, fails

    def aggregate(self, pipeline):
        assert pipeline == [{"$collStats": {"storageStats": {}}}]
        if self.fails:
            raise RuntimeError("$collStats is not here")
        return iter([{"storageStats": self.stats}])


class FakeDb:
    def __init__(self, name, colls):
        self.name, self.colls = name, colls
        self.commands = []

    def command(self, *args):
        self.commands.append(args)
        if args[0] == "dbStats":
            return {"collections": len(self.colls), "objects": 30, "dataSize": 9000, "storageSize": 4096, "indexes": 3,
                    "indexSize": 1024, "totalSize": 5120, "fsUsedSize": 1, "fsTotalSize": 2}
        if args[0] == "collStats":
            return {"count": 7, "size": 700, "storageSize": 512, "nindexes": 1, "totalIndexSize": 64}
        raise AssertionError(args)

    def list_collections(self):
        return iter([{"name": n, "type": "collection"} for n in self.colls] + [{"name": "system.views", "type": "collection"},
                                                                             {"name": "recent", "type": "view"}])

    def __getitem__(self, name):
        return self.colls[name]


class FakeMongo:
    def __init__(self, ping=True):
        self.ping, self.closed = ping, False
        self.dbs = {"liminal": FakeDb("liminal", {"news": FakeColl({"count": 23, "size": 2300, "storageSize": 1024,
                                                                    "nindexes": 2, "totalIndexSize": 128}),
                                                   "gov": FakeColl({}, fails=True)})}
        self.admin = types.SimpleNamespace(command=self._admin)

    def _admin(self, name):
        if name == "ping":
            if not self.ping:
                raise RuntimeError("no server selected")
            return {"ok": 1}
        if name == "serverStatus":
            return {"version": "9.0.4", "uptime": 3600, "pid": 4242, "mem": {"resident": 180}}
        raise AssertionError(name)

    def list_database_names(self):
        return ["admin", "config", "liminal", "local"]

    def __getitem__(self, name):
        return self.dbs[name]

    def close(self):
        self.closed = True


@pytest.fixture
def never_started(monkeypatch):
    """liminal_libs.mongo's start, attach and ensure refuse: the view never starts the server."""
    for name in ("start", "attach", "ensure"):
        monkeypatch.setattr(lib.mongo, name, lambda *a, _n=name, **kw: pytest.fail(f"mongo.{_n} was called"))


def test_mongodb_not_listening_is_not_running_and_no_client_is_made(never_started):
    out = dbs.mongo_figures(lambda: pytest.fail("no client for a port nothing listens at"), lambda h, p: False)
    assert out["running"] is False and out["databases"] == [] and "never started" in out["why"]
    silent = FakeMongo(ping=False)
    out = dbs.mongo_figures(lambda: silent, lambda h, p: True)
    assert out["running"] is False and "ping" in out["why"] and silent.closed


def test_a_running_mongodb_gives_its_databases_and_collections_and_is_let_go(never_started):
    client = FakeMongo()
    out = dbs.mongo_figures(lambda: client, lambda h, p: (h, p) == (lib.mongo.HOST, lib.mongo.port()))
    assert client.closed and out["running"] and (out["version"], out["uptime"], out["residentMB"]) == ("9.0.4", 3600, 180)
    assert out["system"] == ["admin", "config", "local"] and [d["name"] for d in out["databases"]] == ["liminal"]
    d = out["databases"][0]
    assert (d["collections"], d["objects"], d["storageSize"], d["indexSize"]) == (2, 30, 4096, 1024)
    assert [(c["name"], c["count"], c["storageSize"]) for c in d["collectionStats"]] == [("news", 23, 1024), ("gov", 7, 512)]
    assert ("collStats", "gov") in client.dbs["liminal"].commands  # $collStats refused: the command instead


def test_the_real_openers_are_read_only_and_local(monkeypatch):
    seen = []
    fake = types.ModuleType("pymongo")
    fake.MongoClient = lambda *a, **kw: seen.append((a, kw)) or "client"
    monkeypatch.setitem(sys.modules, "pymongo", fake)
    assert mongo_client() == "client"
    (host, port), kw = seen[0]
    assert host == "127.0.0.1" and port == lib.mongo.port() and kw["directConnection"] is True
    assert kw["serverSelectionTimeoutMS"] <= 1000
    tried = []

    def refused(address, timeout):
        tried.append((address, timeout))
        raise ConnectionRefusedError(address)
    monkeypatch.setattr(dbs.socket, "create_connection", refused)
    assert port_open("127.0.0.1", 27017) is False and tried == [(("127.0.0.1", 27017), 0.3)]


# -- the folder, the growth, the view's two asks -------------------------------------------------
def _folder(tmp_path):
    """A data folder of stand-in files (plain bytes, not databases), their times set."""
    files = {"liminal.db": 1000, "liminal.db-wal": 200, "liminal.db-shm": 32, "feeds/a.db": 5000, "feeds/a-ticks.db": 10,
             "history/a/2026-01.1.duckdb": 300, "history/a/2026-01.1.duckdb.wal": 5, "history/a/2026-02.1.duckdb": 400,
             "history/a/2026-03.1.duckdb.part": 50, "datasets/x.db": 20, "backups/old/b.db": 7, "logs/liminal.log": 99,
             "mongo/collection-0.wt": 100, "mongo/journal/WiredTigerLog.1": 60, "notes.txt": 3, "paper/liminal.db": 1}
    for rel, size in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\0" * size)
    os.utime(tmp_path / "liminal.db", (1_700_001_000, 1_700_001_000))
    os.utime(tmp_path / "liminal.db-wal", (1_700_002_000, 1_700_002_000))
    os.utime(tmp_path / "liminal.db-shm", (1_700_003_000, 1_700_003_000))  # touched by readers too: not a write
    return files


def test_the_list_holds_every_database_with_its_side_files_and_opens_none(tmp_path):
    _folder(tmp_path)
    d = dbs.Databases(tmp_path, clock=Clock())
    out = d.overview()
    by = {e["id"]: e for e in out["entries"]}
    assert [g["id"] for g in out["groups"]] == ["main", "feeds", "history", "datasets", "backups", "other", "mongodb"]
    assert [e["id"] for e in out["entries"]] == ["liminal.db", "feeds/a.db", "feeds/a-ticks.db", "history/a/", "datasets/x.db",
                                                 "backups/old/b.db", "paper/liminal.db", "mongodb"]  # as the list shows them
    # no log, no text file, MongoDB's files its own entry
    main = by["liminal.db"]
    assert (main["size"], main["file"], main["side"], main["engine"], main["group"], main["name"]) == (
        1232, 1000, {"wal": 200, "shm": 32}, "sqlite", "main", "liminal")
    assert main["modified"] == "2023-11-14T22:46:40+00:00"  # the -wal's time, not the -shm's
    h = by["history/a/"]
    assert (h["engine"], h["files"], h["copying"], h["size"], h["manifest"]) == ("duckdb", 2, 50, 755, "feeds/a.db")
    assert (by["backups/old/b.db"]["name"], by["paper/liminal.db"]["group"], by["paper/liminal.db"]["name"]) == ("old/b", "other", "paper/liminal")
    m = by["mongodb"]
    assert (m["state"], m["size"]) == ("not running", 160) and out["mongo"]["running"] is False and out["mongo"]["disk"] == 160
    assert out["totals"]["size"] == sum(e["size"] for e in out["entries"]) and all(e["growth"] is None for e in out["entries"])


def test_growth_an_hour_comes_from_the_pages_own_samples(tmp_path):
    _folder(tmp_path)
    clock = Clock(1_000_000.0)
    d = dbs.Databases(tmp_path, clock=clock)
    assert d.overview()["entries"][0]["growth"] is None  # a first look: nothing to compare
    with open(tmp_path / "liminal.db-wal", "ab") as f:
        f.write(b"\0" * 1800)
    clock.t += 30  # listed again, but too soon to tell
    first = {e["id"]: e for e in d.overview()["entries"]}["liminal.db"]
    assert first["size"] == 3032 and first["growth"] is None
    clock.t += 90  # two minutes since the first look: 1800 bytes in 120 s
    later = {e["id"]: e for e in d.overview()["entries"]}["liminal.db"]
    assert later["growth"] == pytest.approx(1800 * 3600 / 120) and later["growthSpan"] == pytest.approx(120)
    g = dbs.Growth()
    for minute in range(0, 181, 1):  # three hours watched: the rate over the last hour alone
        g.add(minute * 60.0, {"x": 1000 if minute <= 120 else 1000 + (minute - 120) * 100})
    rate, span = g.rate("x", 1000 + 60 * 100, 180 * 60.0)
    assert span == pytest.approx(3600) and rate == pytest.approx(6000)
    away = dbs.Growth()
    away.add(0.0, {"x": 0})
    rate, span = away.rate("x", 7200, 7200.0)  # the page away two hours: over those two hours
    assert (rate, span) == (pytest.approx(3600), 7200.0)


def test_a_database_is_opened_for_its_page_once_a_while_and_its_figures_kept(tmp_path):
    _folder(tmp_path)
    clock, opened = Clock(), []
    conn = FakeSqlite(schema=[table("kv", 2)], counts={"kv": 5})

    def opener(path):
        opened.append(path)
        conn.closed = False
        return conn
    d = dbs.Databases(tmp_path, sqlite=opener, clock=clock)
    one = d.detail("liminal.db")
    assert opened == [tmp_path / "liminal.db"] and conn.closed and one["figures"]["tables"] == [
        {"name": "kv", "rows": 5, "how": "counted", "withoutRowid": False, "indexes": 0}]
    assert one["size"] == 1232 and one["readAt"] and one["server"] is None
    clock.t += dbs.DETAIL_S - 1
    assert d.detail("liminal.db")["figures"]["tables"][0]["rows"] == 5 and len(opened) == 1  # kept: nothing opened
    assert {e["id"]: e for e in d.overview()["entries"]}["liminal.db"]["rows"] == 5  # the list shows what was read
    clock.t += 2
    d.detail("liminal.db")
    assert len(opened) == 2  # read again once DETAIL_S passed
    with pytest.raises(LookupError):
        d.detail("nowhere.db")


def test_a_databases_failure_is_its_pages_error_not_the_views(tmp_path):
    _folder(tmp_path)

    def busy(path):
        raise sqlite3.OperationalError("database is locked")
    out = dbs.Databases(tmp_path, sqlite=busy, clock=Clock()).detail("feeds/a.db")
    assert out["figures"]["error"] == "OperationalError: database is locked" and out["size"] == 5000


def test_a_feeds_months_on_its_page_read_its_feed_files_manifest(tmp_path):
    _folder(tmp_path)
    opened = []

    def opener(path):
        opened.append(path)
        return FakeSqlite(manifest=[("2026-01", "2026-01.1.duckdb", 70, 3, 300, 0, 1.0, 0),
                                    ("2026-02", "2026-02.1.duckdb", 80, 0, 400, 0, 1.0, 0)])
    out = dbs.Databases(tmp_path, sqlite=opener, clock=Clock()).detail("history/a/")
    assert opened == [tmp_path / "feeds" / "a.db"]  # the feed's SQLite file, never a month file
    f = out["figures"]
    assert (f["bars"], f["built"], [u["state"] for u in f["unlisted"]]) == (150, 3, ["copying"])


def test_mongodb_running_lists_its_databases_and_their_collections(tmp_path, never_started):
    _folder(tmp_path)
    client = FakeMongo()
    d = dbs.Databases(tmp_path, mongo=lambda: client, listening=lambda h, p: True, clock=Clock())
    out = d.overview()
    by = {e["id"]: e for e in out["entries"]}
    assert "mongodb" not in by and by["mongodb/liminal"]["rows"] == 30 and by["mongodb/liminal"]["size"] == 4096
    assert out["mongo"]["running"] and out["mongo"]["version"] == "9.0.4" and out["mongo"]["disk"] == 160
    one = d.detail("mongodb/liminal")
    assert [(t["name"], t["rows"]) for t in one["figures"]["tables"]] == [("news", 23), ("gov", 7)]
    assert one["server"]["version"] == "9.0.4" and client.closed


# -- the routes ----------------------------------------------------------------------------------
def test_the_integrators_frame_answers_the_databases_view(tmp_path):
    _folder(tmp_path)
    app = IntegratorApp(log=lambda m: None, db_path=tmp_path / "liminal.db")
    assert app.databases.data_dir == tmp_path and app.databases is app.databases  # one, made at the first ask
    app._databases = dbs.Databases(tmp_path, sqlite=lambda p: FakeSqlite(schema=[table("kv", 2)], counts={"kv": 1}),
                                   clock=Clock())
    status, out = app.api(None, "GET", "/api/databases", {}, None)
    assert status == 200 and out["root"] == str(tmp_path) and len(out["entries"]) == 8
    status, one = app.api(None, "GET", "/api/databases/detail", {"id": "liminal.db"}, None)
    assert status == 200 and one["figures"]["tables"][0]["rows"] == 1
    for query, code in (({}, HTTPStatus.BAD_REQUEST), ({"id": "nope.db"}, HTTPStatus.NOT_FOUND)):
        with pytest.raises(lib.Refused) as e:
            app.api(None, "GET", "/api/databases/detail", query, None)
        assert e.value.status == code
    assert app.api(None, "GET", "/api/app", {}, None)[1]["app"] == "integrator"  # the frame's own routes still
    with pytest.raises(lib.Refused):
        app.api(None, "GET", "/api/nothing", {}, None)
    assert IntegratorApp(log=lambda m: None).databases.data_dir == lib.layout.data_dir()  # no database named: the workspace's
