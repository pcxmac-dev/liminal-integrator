"""The databases themselves, for the integrator's page (its Databases view). The user, 2026-11-07: "the
integrator will have stats for the databases themselves, the platform only cares about hardware". The
integrator is the keeper of the stored data, so its page says what is kept:

- every SQLite and DuckDB file in the data folder (liminal.db, feeds/<feed>.db and <feed>-ticks.db, the
  closed months in history/<feed>/<YYYY-MM>.<n>.duckdb, datasets/, gov/, the login's, the backups ...):
  its size on disk (its -wal and -shm files with it), its growth an hour, when it was last written, and
  its tables' row counts;
- Liminal's MongoDB (liminal_libs.mongo, its data in the data folder's mongo/): its databases and
  collections with their counts and storage sizes (dbStats, $collStats), only while the server already
  runs: it is never started to be asked (a TCP check of its port first, then a ping).

Nothing runs for nobody (the user, 2026-11-01: "i cant have open databases and processes when im not
using the app or plugin directly"): no thread of its own; the folder is listed (sizes and times, no
database opened) when the page asks, at most every LIST_S, and a database is opened read-only (SQLite
`mode=ro` and query-only, DuckDB `read_only`) only for the moment its figures are read, when the page
shows it, and closed at once; one database at a time, its figures kept DETAIL_S so a page asking again
opens nothing. Growth is measured from the sizes the page's own asks sampled (at most every SAMPLE_S,
a little over an hour kept): over the last hour, or over a longer span when the page was away.

A count never scans a large table (a feed's bars: billions of rows in a terabyte). A table is counted
outright only when that is cheap: its file under EXACT_BYTES, or a table its B-tree puts under
EXACT_ROWS, and even then within COUNT_BUDGET_S. A larger one has SQLite's own statistics when the file
was analysed (sqlite_stat1), else an estimate from its B-tree: a few dozen root-to-leaf paths read
straight from the file (Knuth's estimator; the pages, never the table). A feed's DuckDB months have the
rows the manifest in the feed's SQLite file counted when each was copied (liminal_libs'
storage/history.py), so no month file is opened; any other DuckDB file has its own table statistics
(duckdb_tables().estimated_size).
"""
from __future__ import annotations

import os
import random
import re
import socket
import sqlite3
import struct
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import lib

LIST_S = 5.0  # the folder listed at most this often (the view asks every 10 s)
SAMPLE_S = 60.0  # a size sample kept at most this often
GROWTH_S = 3600.0  # growth over the last hour ...
MIN_SPAN_S = 60.0  # ... once the samples span this long
SAMPLES = 72  # kept: a little over an hour at SAMPLE_S
DETAIL_S = 60.0  # a database's figures read again after this long (opened at most this often)
DETAILS = 64  # figures kept at most (the oldest dropped first)
MONGO_S = 30.0  # the server asked again after this long
EXACT_BYTES = 64 * 2**20  # a SQLite file this small: its tables counted outright
EXACT_ROWS = 200_000  # a table its B-tree puts under this: counted outright
COUNT_BUDGET_S = 2.0  # counting outright stops after this long a database (the estimate stays)
PROBES = 48  # root-to-leaf paths read for a B-tree's estimate
MAX_DEPTH = 24  # a path deeper than this is a broken one
KEEP_PAGES = 256  # a tree's top pages kept while one estimate reads it
PENDING_BYTE = 0x40000000  # SQLite's lock page holds it: never a B-tree page
MAX_FILES = 50_000  # files listed at most

SQLITE = (".db", ".sqlite", ".sqlite3")
DUCKDB = (".duckdb",)
SQLITE_SIDE = ("-wal", "-shm", "-journal")  # beside a SQLite file
DUCKDB_SIDE = (".wal",)
WRITTEN_SIDE = ("-wal", "-journal", ".wal")  # what a write touches (-shm changes on reads too)
SKIP = {"mongo", "logs"}  # top folders that hold no database file (MongoDB's own: its entry)
MONTH_FILE = re.compile(r"^(\d{4}-\d{2})\.(\d+)\.duckdb$")
MONTH_PART = re.compile(r"^\d{4}-\d{2}\.\d+\.duckdb\.part(\.wal)?$")
SYSTEM_DBS = ("admin", "config", "local")  # MongoDB's own

# The list's groups, in order: the top folder a file is in, and what it holds.
GROUPS = (
    ("main", "Main", "the integrator's own database: symbols, the request stack, the fetch queue, the runs"),
    ("feeds", "Feeds", "each feed's bars (SQLite); its trades in <feed>-ticks"),
    ("history", "History", "each feed's closed months copied to DuckDB, a file a month (the manifest in the feed's file)"),
    ("datasets", "Datasets", "the research series (Fama/French, Shiller, CFTC, IMF, the S&P 500's constituents)"),
    ("gov", "Federal", "the federal agencies' items and parameters"),
    ("login", "Login", "the login app's users and their sealed vaults"),
    ("backups", "Backups", "copies kept before a migration"),
    ("other", "Elsewhere", "elsewhere in the data folder"),
    ("mongodb", "MongoDB", "documents (headlines, filings, releases) where a plugin keeps them in MongoDB"),
)
FOLDERS = {"": "main", "feeds": "feeds", "history": "history", "datasets": "datasets", "gov": "gov", "login": "login",
           "backups": "backups"}

Log = Callable[[str], None]


def _iso(t: float | None) -> str | None:
    return None if t is None else datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# -- the openers (module names, so a test stands them in: tests/conftest.py refuses the real ones) --
def connect_sqlite(path: Path) -> sqlite3.Connection:
    """A SQLite file opened read-only (mode=ro, query-only): its writers go on, nothing is written."""
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=1.0, check_same_thread=False)
    conn.execute("PRAGMA query_only=ON")
    return conn


def connect_duckdb(path: Path):
    """A DuckDB file opened read-only (a file a writer holds refuses: it is said so)."""
    import duckdb

    return duckdb.connect(str(path), read_only=True, config={"threads": 1, "memory_limit": "64MB"})


def mongo_client(timeout_ms: int = 800):
    """A client of the server here (127.0.0.1 only), for one read: closed after it."""
    from pymongo import MongoClient

    return MongoClient(lib.mongo.HOST, lib.mongo.port(), serverSelectionTimeoutMS=timeout_ms, connectTimeoutMS=timeout_ms,
                       socketTimeoutMS=5000, directConnection=True, appname="liminal-integrator")


def port_open(host: str, port: int, timeout: float = 0.3) -> bool:
    """Whether something listens at host:port (a refused connection answers at once: no server
    selection to wait out when MongoDB is not running)."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# -- growth ------------------------------------------------------------------------------------
class Growth:
    """The databases' sizes sampled at most every SAMPLE_S, when the page asks, SAMPLES kept: a
    database's growth an hour over the last hour, or over the span the samples have (a page away
    for a while: since its last look; a first look: none until they span MIN_SPAN_S)."""

    def __init__(self, keep: int = SAMPLES):
        self.samples: deque[tuple[float, dict[str, int]]] = deque(maxlen=keep)

    def add(self, at: float, sizes: dict[str, int]) -> None:
        if not self.samples or at - self.samples[-1][0] >= SAMPLE_S:
            self.samples.append((at, dict(sizes)))

    def rate(self, key: str, size: int, at: float) -> tuple[float | None, float | None]:
        """(bytes an hour, over how many seconds), or (None, None) while unknown."""
        then = None
        for t, sizes in self.samples:  # oldest first: the newest at least an hour old, else the oldest
            if key not in sizes:
                continue
            if at - t >= GROWTH_S:
                then = (t, sizes[key])
            elif then is None:
                then = (t, sizes[key])
                break
            else:
                break
        if then is None or at - then[0] < MIN_SPAN_S:
            return None, None
        span = at - then[0]
        return (size - then[1]) * 3600.0 / span, span


# -- a SQLite file's B-tree, read straight from the file ------------------------------------------
class PageReader:
    """A SQLite file's pages read straight from it (no connection, no lock: the pages as the file
    holds them, the newest writes still in its -wal left out), the top of a tree kept while one
    estimate reads it."""

    def __init__(self, path: Path, page_size: int):
        self.path, self.page_size = Path(path), int(page_size)
        self.pages = 0
        self.lock_page = PENDING_BYTE // self.page_size + 1
        self._f = None
        self._kept: dict[int, bytes] = {}

    def __enter__(self) -> PageReader:
        self._f = open(self.path, "rb", buffering=0)
        self.pages = os.fstat(self._f.fileno()).st_size // self.page_size
        return self

    def __exit__(self, *exc) -> None:
        if self._f is not None:
            self._f.close()
            self._f = None
        self._kept.clear()

    def page(self, n: int, keep: bool = False) -> bytes:
        got = self._kept.get(n)
        if got is not None:
            return got
        if not 1 <= n <= self.pages or n == self.lock_page:
            raise ValueError(f"page {n} is not in the file")
        self._f.seek((n - 1) * self.page_size)
        data = self._f.read(self.page_size)
        if len(data) != self.page_size:
            raise ValueError(f"page {n}: a short read")
        if keep and len(self._kept) < KEEP_PAGES:
            self._kept[n] = data
        return data


def btree_entries(page: Callable[[int, bool], bytes], root: int, index: bool, probes: int = PROBES,
                  rng: random.Random | None = None) -> float | None:
    """The entries of a B-tree estimated from `probes` random paths from its root to a leaf (Knuth,
    1975: each path's product of fan-outs times what it meets is an unbiased estimate of the whole).
    `index`: an index tree (a WITHOUT ROWID table's, an index's), whose interior cells are entries
    too; else a table tree (a rowid table's: its rows in the leaves alone). `page(n, keep)` gives page
    n's bytes (keep: a top page, read again by the next path). None if no path could be read (a tree
    still in the -wal, a page torn by a checkpoint going on)."""
    rng = rng or random.Random(root)
    interior, leaf = (2, 10) if index else (5, 13)
    total, good = 0.0, 0
    for _ in range(probes):
        n, depth, mult, found = root, 0, 1.0, 0.0
        try:
            while True:
                if depth >= MAX_DEPTH:
                    raise ValueError("too deep")
                data = page(n, depth < 3)
                at = 100 if n == 1 else 0  # page 1 starts with the file's header
                kind = data[at]
                cells = struct.unpack_from(">H", data, at + 3)[0]
                if kind == leaf:
                    found += mult * cells
                    break
                if kind != interior or at + 12 + 2 * cells > len(data):
                    raise ValueError(f"page {n} is not this tree's (type {kind})")
                if index:
                    found += mult * cells
                k = rng.randrange(cells + 1)
                if k == cells:
                    child = struct.unpack_from(">I", data, at + 8)[0]  # the right-most child
                else:
                    cell = struct.unpack_from(">H", data, at + 12 + 2 * k)[0]
                    if cell + 4 > len(data):
                        raise ValueError(f"page {n}: a cell outside it")
                    child = struct.unpack_from(">I", data, cell)[0]
                mult *= cells + 1
                n, depth = child, depth + 1
        except (ValueError, IndexError, struct.error, OSError):
            continue  # this path broke: the others decide
        total += found
        good += 1
    return total / good if good else None


def _without_rowid(sql: str | None) -> bool:
    tail = (sql or "")[(sql or "").rfind(")") + 1:].upper()
    return "WITHOUT" in tail and "ROWID" in tail


def _count(conn, table: str, deadline: float, clock: Callable[[], float]) -> int | None:
    """COUNT(*) of a table, given up (None) once `deadline` passes."""
    if clock() >= deadline:
        return None
    conn.set_progress_handler(lambda: 1 if clock() >= deadline else 0, 20_000)
    try:
        return int(conn.execute(f"SELECT count(*) FROM {_quoted(table)}").fetchone()[0])
    except sqlite3.OperationalError:  # interrupted: too large to count cheaply
        return None
    finally:
        conn.set_progress_handler(None, 0)


def sqlite_figures(path: Path, size: int, connect: Callable[[Path], object], pages: Callable[[Path, int], PageReader],
                   clock: Callable[[], float] = time.monotonic) -> dict:
    """A SQLite file's own figures, read-only and at once: its page size and pages, free pages, journal
    mode, user version, and each table's rows (counted, from SQLite's statistics, or estimated from
    its B-tree: `how`), largest first; the connection closed before returning."""
    conn = connect(path)
    try:
        one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        page_size, page_count, free = int(one("PRAGMA page_size")), int(one("PRAGMA page_count")), int(one("PRAGMA freelist_count"))
        journal, user_version = str(one("PRAGMA journal_mode")), int(one("PRAGMA user_version"))
        schema = [tuple(r) for r in conn.execute("SELECT type, name, tbl_name, rootpage, sql FROM sqlite_master")]
        stats: dict[str, int] = {}
        if any(t == "table" and name == "sqlite_stat1" for t, name, *_ in schema):
            for tbl, _idx, stat in conn.execute("SELECT tbl, idx, stat FROM sqlite_stat1"):
                head = str(stat or "").split(" ", 1)[0]
                if head.isdigit():
                    stats[tbl] = max(stats.get(tbl, 0), int(head))
        indexes: dict[str, int] = {}
        for t, _name, tbl, *_ in schema:
            if t == "index":
                indexes[tbl] = indexes.get(tbl, 0) + 1
        small = size <= EXACT_BYTES
        deadline = clock() + COUNT_BUDGET_S
        tables, reader = [], None
        try:
            for t, name, _tbl, root, sql in schema:
                if t != "table" or name.startswith("sqlite_"):
                    continue
                row = {"name": name, "rows": None, "how": "unknown", "withoutRowid": _without_rowid(sql),
                       "indexes": indexes.get(name, 0)}
                tables.append(row)
                if not root:  # a virtual table: its rows are its module's
                    row["how"] = "virtual"
                    continue
                if small and (n := _count(conn, name, deadline, clock)) is not None:
                    row.update(rows=n, how="counted")
                    continue
                if name in stats:
                    row.update(rows=stats[name], how="statistics")
                    continue
                if reader is None:
                    try:
                        reader = pages(path, page_size).__enter__()
                    except (OSError, ValueError):  # the file not readable as pages here: these tables not counted
                        reader = False
                if reader is False:
                    continue
                est = btree_entries(reader.page, int(root), row["withoutRowid"],
                                    rng=random.Random(f"{root}:{page_count}"))  # the same file, the same estimate
                if est is None:
                    continue
                if est < EXACT_ROWS and (n := _count(conn, name, deadline, clock)) is not None:
                    row.update(rows=n, how="counted")
                else:
                    row.update(rows=int(round(est)), how="estimated")
        finally:
            if reader:
                reader.__exit__(None, None, None)
    finally:
        conn.close()
    tables.sort(key=lambda r: (r["rows"] is None, -(r["rows"] or 0), r["name"]))
    return {"engine": "sqlite", "pageSize": page_size, "pages": page_count, "freePages": free, "journal": journal,
            "userVersion": user_version, "statistics": bool(stats), "sqlite": sqlite3.sqlite_version, "tables": tables,
            "indexes": sum(indexes.values())}


def duckdb_figures(path: Path, connect: Callable[[Path], object]) -> dict:
    """A DuckDB file's tables and their rows from its own table statistics, read-only; closed after."""
    conn = connect(path)
    try:
        rows = conn.execute("SELECT schema_name, table_name, estimated_size, column_count, index_count "
                            "FROM duckdb_tables() WHERE NOT internal AND NOT temporary").fetchall()
        try:
            version = conn.execute("SELECT library_version FROM pragma_version()").fetchone()[0]
        except Exception:  # noqa: BLE001 - only said when known
            version = None
    finally:
        conn.close()
    tables = [{"name": t if s == "main" else f"{s}.{t}", "rows": None if n is None else int(n), "how": "statistics",
               "columns": c, "indexes": i} for s, t, n, c, i in rows]
    tables.sort(key=lambda r: (r["rows"] is None, -(r["rows"] or 0), r["name"]))
    return {"engine": "duckdb", "duckdb": version, "tables": tables}


def history_figures(feed_db: Path | None, files: list[tuple[str, int, float]], connect: Callable[[Path], object]) -> dict:
    """A feed's closed months in DuckDB: the manifest in the feed's SQLite file (each month's file, its
    rows copied from bars and built_bars, its size, when copied, whether written in SQLite since) read
    read-only, against the files on disk (a file the manifest does not name: a copy going on, or one
    superseded and left for the next run's tidy). No month file is opened."""
    rows, manifest = [], None
    if feed_db is not None and feed_db.is_file():
        conn = connect(feed_db)
        try:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='history'").fetchone():
                manifest = feed_db.name
                rows = [tuple(r) for r in conn.execute("SELECT month, file, bars, built, bytes, archived_at, seconds, stale "
                                                       "FROM history ORDER BY month")]
        finally:
            conn.close()
    on_disk = {name: (size, mtime) for name, size, mtime in files}
    named = set()
    months = []
    for month, file, bars, built, nbytes, archived_at, seconds, stale in rows:
        named.add(file)
        disk = on_disk.get(file)
        months.append({"month": month, "file": file, "bars": bars, "built": built, "bytes": nbytes,
                       "copiedAt": _iso(archived_at / 1000) if archived_at else None, "seconds": seconds,
                       "stale": bool(stale), "onDisk": disk[0] if disk else None})
    unlisted = []
    for name, size, mtime in sorted(files):
        if name in named or (name.endswith(".wal") and name[:-4] in named):
            continue
        state = "copying" if MONTH_PART.match(name) else "superseded" if manifest else "unlisted"
        unlisted.append({"file": name, "size": size, "modified": _iso(mtime), "state": state})
    return {"engine": "duckdb", "manifest": manifest, "months": months[::-1], "unlisted": unlisted,
            "bars": sum(m["bars"] or 0 for m in months), "built": sum(m["built"] or 0 for m in months),
            "stale": sum(m["stale"] for m in months), "missing": sum(m["onDisk"] is None for m in months),
            "tables": [{"name": "bars", "rows": sum(m["bars"] or 0 for m in months), "how": "manifest"},
                       {"name": "built_bars", "rows": sum(m["built"] or 0 for m in months), "how": "manifest"}]}


def _coll_stats(db, name: str) -> dict:
    """One collection's count and sizes from its storage statistics ($collStats; the collStats command
    on a server without it): from the server's metadata, no document read."""
    try:
        doc = next(iter(db[name].aggregate([{"$collStats": {"storageStats": {}}}])), None)
        s = (doc or {}).get("storageStats") or {}
    except Exception:  # noqa: BLE001 - an older server: the command
        s = db.command("collStats", name)
    return {"name": name, "count": s.get("count"), "size": s.get("size"), "storageSize": s.get("storageSize"),
            "indexes": s.get("nindexes"), "indexSize": s.get("totalIndexSize"), "avgObjSize": s.get("avgObjSize")}


def mongo_figures(client_factory: Callable[[], object], listening: Callable[[str, int], bool]) -> dict:
    """Liminal's MongoDB, only when it runs already: its port checked, then a ping; never started
    (liminal_libs.mongo.attach/ensure/start are not called). Its version and uptime, and each of its
    databases (not MongoDB's own) with dbStats and each collection's storage statistics."""
    host, port = lib.mongo.HOST, lib.mongo.port()
    out = {"host": host, "port": port, "running": False, "databases": [], "system": []}
    if not listening(host, port):
        out["why"] = "not running (nothing listens at its port); never started to be asked"
        return out
    try:
        client = client_factory()
    except ImportError:
        out["why"] = "pymongo is not installed here"
        return out
    try:
        try:
            client.admin.command("ping")
        except Exception as e:  # noqa: BLE001 - something else at the port, or a server starting
            out["why"] = f"no answer to a ping ({type(e).__name__})"
            return out
        status = client.admin.command("serverStatus")
        out.update(running=True, version=status.get("version"), uptime=status.get("uptime"), pid=status.get("pid"),
                   residentMB=(status.get("mem") or {}).get("resident"))
        for name in sorted(client.list_database_names()):
            if name in SYSTEM_DBS:
                out["system"].append(name)
                continue
            db = client[name]
            st = db.command("dbStats")
            collections = []
            for c in sorted(db.list_collections(), key=lambda c: c.get("name", "")):
                cname = c.get("name", "")
                if cname.startswith("system.") or c.get("type", "collection") != "collection":
                    continue
                try:
                    collections.append(_coll_stats(db, cname))
                except Exception as e:  # noqa: BLE001 - this collection's figures alone are missing
                    collections.append({"name": cname, "error": f"{type(e).__name__}: {e}"})
            collections.sort(key=lambda c: (-(c.get("count") or 0), c["name"]))
            out["databases"].append({
                "name": name, "collections": st.get("collections"), "objects": st.get("objects"),
                "dataSize": st.get("dataSize"), "storageSize": st.get("storageSize"), "indexes": st.get("indexes"),
                "indexSize": st.get("indexSize"), "totalSize": st.get("totalSize"), "avgObjSize": st.get("avgObjSize"),
                "fsUsedSize": st.get("fsUsedSize"), "fsTotalSize": st.get("fsTotalSize"), "collectionStats": collections})
    except Exception as e:  # noqa: BLE001 - what was read is shown, and why the rest is not
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        client.close()
    return out


# -- the folder ----------------------------------------------------------------------------------
def walk(root: Path, skip: set[str] = SKIP, limit: int = MAX_FILES) -> list[tuple[str, int, float]]:
    """Every file under `root` as (its path from root, with /; its size; when modified), the top
    folders in `skip` left out. Stat calls alone: nothing is opened."""
    out: list[tuple[str, int, float]] = []
    stack = [(Path(root), "")]
    while stack and len(out) < limit:
        d, rel = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if not (rel == "" and e.name in skip):
                                stack.append((Path(e.path), f"{rel}{e.name}/"))
                        elif e.is_file(follow_symlinks=False):
                            st = e.stat(follow_symlinks=False)
                            out.append((f"{rel}{e.name}", st.st_size, st.st_mtime))
                    except OSError:
                        continue
        except OSError:
            continue
    return out


def engine_of(name: str) -> str | None:
    low = name.lower()
    if low.endswith(DUCKDB):
        return "duckdb"
    if low.endswith(SQLITE):
        return "sqlite"
    return None


def catalog(root: Path, files: list[tuple[str, int, float]]) -> tuple[list[dict], dict[str, list[tuple[str, int, float]]]]:
    """The databases among `files` (walk): one entry a SQLite or DuckDB file, its side files (-wal,
    -shm, -journal; .wal) counted in its size; a feed's month files in history/<feed>/ one entry a feed
    (its copies going on with it). Returns the entries and each feed's month files."""
    by_path = {rel: (size, mtime) for rel, size, mtime in files}
    entries: list[dict] = []
    months: dict[str, list[tuple[str, int, float]]] = {}
    for rel, size, mtime in sorted(files):
        parts = rel.split("/")
        if len(parts) == 3 and parts[0] == "history" and (MONTH_FILE.match(parts[2]) or MONTH_PART.match(parts[2])
                                                           or (parts[2].endswith(".duckdb.wal") and MONTH_FILE.match(parts[2][:-4]))):
            months.setdefault(parts[1], []).append((parts[2], size, mtime))
            continue
        engine = engine_of(rel)
        if engine is None:
            continue
        side = {}
        for suffix in SQLITE_SIDE if engine == "sqlite" else DUCKDB_SIDE:
            got = by_path.get(rel + suffix)
            if got is not None:
                side[suffix.lstrip("-.")] = got
        written = max([mtime] + [by_path[rel + s][1] for s in WRITTEN_SIDE if rel + s in by_path])
        top = parts[0] if len(parts) > 1 else ""
        group = FOLDERS.get(top, "other")
        stem = rel[: -len(Path(rel).suffix)] if Path(rel).suffix else rel
        name = stem if group == "other" else stem.split("/", 1)[1] if "/" in stem else stem
        entries.append({"id": rel, "name": name, "group": group, "engine": engine, "kind": "file",
                        "path": str(Path(root) / rel), "size": size + sum(s for s, _ in side.values()), "file": size,
                        "side": {k: s for k, (s, _) in side.items()}, "modifiedAt": written})
    for feed, got in sorted(months.items()):
        copying = sum(s for n, s, _ in got if MONTH_PART.match(n))
        entries.append({"id": f"history/{feed}/", "name": feed, "group": "history", "engine": "duckdb", "kind": "history",
                        "path": str(Path(root) / "history" / feed), "size": sum(s for _, s, _ in got),
                        "files": sum(1 for n, _, _ in got if MONTH_FILE.match(n)), "copying": copying,
                        "manifest": f"feeds/{feed}.db", "modifiedAt": max(m for _, _, m in got)})
    return entries, months


# -- what the page asks --------------------------------------------------------------------------
class Databases:
    """The Databases view's figures for one data folder (the integrator's page holds one: app.py)."""

    def __init__(self, data_dir: Path, *, sqlite: Callable | None = None, duckdb: Callable | None = None,
                 mongo: Callable | None = None, listening: Callable | None = None, pages: Callable | None = None,
                 clock: Callable[[], float] = time.time, log: Log = print):
        self.data_dir = Path(data_dir)
        self._openers = {"sqlite": sqlite, "duckdb": duckdb, "mongo": mongo, "listening": listening, "pages": pages}
        self.clock = clock
        self.log = log
        self.growth = Growth()
        self._lock = threading.Lock()  # the listing and the samples
        self._reading = threading.Lock()  # one database opened at a time
        self._asking = threading.Lock()  # one MongoDB client at a time
        self._listed: tuple[float, list[dict], dict] | None = None
        self._mongo: tuple[float, dict] | None = None
        self._mongo_dir: dict = {}
        self._details: dict[str, tuple[float, dict]] = {}

    def _opener(self, kind: str) -> Callable:
        # looked up when used: a test's stand-in (tests/conftest.py) replaces the module's
        given = self._openers[kind]
        if given is not None:
            return given
        return {"sqlite": connect_sqlite, "duckdb": connect_duckdb, "mongo": mongo_client, "listening": port_open,
                "pages": PageReader}[kind]

    # -- the listing (no database opened) ------------------------------------------------------
    def _list(self) -> tuple[float, list[dict], dict]:
        with self._lock:
            now = self.clock()
            if self._listed is not None and now - self._listed[0] < LIST_S:
                return self._listed
            entries, months = catalog(self.data_dir, walk(self.data_dir))
            mongo_files = walk(self.data_dir / lib.layout.MONGO, skip=set())
            self._mongo_dir = {"size": sum(s for _, s, _ in mongo_files), "files": len(mongo_files),
                               "modifiedAt": max((m for _, _, m in mongo_files), default=None),
                               "path": str(self.data_dir / lib.layout.MONGO)}
            sizes = {e["id"]: e["size"] for e in entries}
            if mongo_files:
                sizes["mongodb"] = self._mongo_dir["size"]
            if self._mongo is not None:
                for d in self._mongo[1].get("databases", []):
                    sizes[f"mongodb/{d['name']}"] = d.get("storageSize") or 0
            self.growth.add(now, sizes)
            for e in entries:
                e["growth"], e["growthSpan"] = self.growth.rate(e["id"], e["size"], now)
            self._listed = (now, entries, months)
            return self._listed

    def _mongo_now(self) -> dict:
        with self._asking:
            if self._mongo is None or self.clock() - self._mongo[0] >= MONGO_S:
                self._mongo = (self.clock(), mongo_figures(self._opener("mongo"), self._opener("listening")))
            return self._mongo[1]

    def overview(self) -> dict:
        """The list: every database with its size, growth and last write (the files' own figures),
        and MongoDB's databases when it runs; nothing opened but the server asked (MONGO_S)."""
        now, entries, _ = self._list()
        mongo = self._mongo_now()
        rows = [{k: v for k, v in e.items() if k != "modifiedAt"} | {"modified": _iso(e["modifiedAt"])} for e in entries]
        for r in rows:
            cached = self._details.get(r["id"])
            if cached is not None:
                r["tables"] = len(cached[1].get("tables") or [])
                r["rows"] = sum(t.get("rows") or 0 for t in cached[1].get("tables") or [])
        folder = self._mongo_dir
        growth, span = self.growth.rate("mongodb", folder.get("size") or 0, now) if folder.get("files") else (None, None)
        server = {k: v for k, v in mongo.items() if k != "databases"} | {
            "disk": folder.get("size"), "diskFiles": folder.get("files"), "diskPath": folder.get("path"),
            "modified": _iso(folder.get("modifiedAt")), "growth": growth, "growthSpan": span}
        if mongo.get("running"):
            for d in mongo.get("databases", []):
                key = f"mongodb/{d['name']}"
                size = d.get("storageSize") or 0
                g, s = self.growth.rate(key, size, now)
                rows.append({"id": key, "name": d["name"], "group": "mongodb", "engine": "mongodb", "kind": "mongodb",
                             "size": size, "growth": g, "growthSpan": s, "modified": None,
                             "collections": d.get("collections"), "rows": d.get("objects")})
        elif folder.get("files"):
            rows.append({"id": "mongodb", "name": "MongoDB", "group": "mongodb", "engine": "mongodb", "kind": "mongodb-server",
                         "size": folder["size"], "growth": growth, "growthSpan": span, "modified": server["modified"],
                         "state": "not running"})
        order = {g: i for i, (g, _, _) in enumerate(GROUPS)}
        rows.sort(key=lambda r: (order.get(r["group"], len(order)), r["name"].lower()))  # as the list shows them
        seen = {r["group"] for r in rows}
        files = [r for r in rows if r["engine"] != "mongodb"]
        total = sum(r["size"] for r in files) + (folder.get("size") or 0)
        rates = [r["growth"] for r in files if r["growth"] is not None] + ([growth] if growth is not None else [])
        return {"root": str(self.data_dir), "listedAt": _iso(now),
                "groups": [{"id": g, "title": t, "about": a} for g, t, a in GROUPS if g in seen],
                "entries": rows, "mongo": server,
                "totals": {"databases": len(rows), "size": total, "growth": sum(rates) if rates else None},
                "cadence": {"list": LIST_S, "sample": SAMPLE_S, "detail": DETAIL_S, "mongo": MONGO_S},
                "limits": {"exactBytes": EXACT_BYTES, "exactRows": EXACT_ROWS, "probes": PROBES}}

    # -- one database (opened read-only, briefly) ----------------------------------------------
    def detail(self, ident: str) -> dict:
        """One database: its listing's figures and its own (tables and rows; the months; the
        collections), read now unless read within DETAIL_S. LookupError: no such database."""
        overview = self.overview()
        row = next((r for r in overview["entries"] if r["id"] == ident), None)
        if row is None:
            raise LookupError(f"no database {ident!r} in {self.data_dir}")
        now = self.clock()
        cached = self._details.get(ident)
        if cached is None or now - cached[0] >= DETAIL_S:
            with self._reading:
                cached = self._details.get(ident)
                if cached is None or self.clock() - cached[0] >= DETAIL_S:
                    began = time.monotonic()
                    try:
                        figures = self._figures(row)
                    except Exception as e:  # noqa: BLE001 - said on the page: a file in use, one not a database
                        figures = {"error": f"{type(e).__name__}: {e}"}
                    figures["took"] = round(time.monotonic() - began, 3)
                    cached = (self.clock(), figures)
                    self._details[ident] = cached
                    while len(self._details) > DETAILS:
                        self._details.pop(min(self._details, key=lambda k: self._details[k][0]))
        read_at, figures = cached
        return {**row, "figures": figures, "readAt": _iso(read_at), "server": overview["mongo"] if row["engine"] == "mongodb" else None}

    def _figures(self, row: dict) -> dict:
        kind = row["kind"]
        if kind == "file" and row["engine"] == "sqlite":
            return sqlite_figures(Path(row["path"]), row["file"], self._opener("sqlite"), self._opener("pages"))
        if kind == "file":
            return duckdb_figures(Path(row["path"]), self._opener("duckdb"))
        if kind == "history":
            _, _, months = self._list()
            feed_db = self.data_dir / row["manifest"]
            return history_figures(feed_db if feed_db.is_file() else None, months.get(row["name"], []), self._opener("sqlite"))
        mongo = self._mongo_now()
        if kind == "mongodb":
            d = next((d for d in mongo.get("databases", []) if f"mongodb/{d['name']}" == row["id"]), None)
            if d is None:
                return {"error": "no longer on the server"}
            return {"engine": "mongodb", **{k: v for k, v in d.items() if k != "collectionStats"},
                    "tables": [{"name": c["name"], "rows": c.get("count"), "how": "metadata", **c} for c in d.get("collectionStats", [])]}
        return {"engine": "mongodb", "tables": [], "why": mongo.get("why")}
