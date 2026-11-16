"""Two integrators on one database (the user, 2026-11-15: "If i run integrator on both sides, there cannot be any
conflicts, so if one symbol is being operated on, the other integrator would have to operate on another symbol"):
a feed the other installation is fetching is not started here and is waited for, not failed; the fetcher says it is
at work, so the other takes back only what a fetcher that is gone left; one that is offline leaves the requests to
the one that can serve them. The other installation is a second Claims object on the same file (liminal-libs
claims.py); the feeds' runs are fakes; no process starts."""
from __future__ import annotations

import os
import threading
import time
from argparse import Namespace
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from liminal_integrator import fetcher, lib

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)  # a Tuesday, 10:00 ET: the session is on


class FakeAttachment:
    def __init__(self, name, lives=999):
        self.name, self.lives, self.detached, self.host_pid = name, lives, False, 4242

    def alive(self):
        if self.detached:
            return False
        self.lives -= 1
        return self.lives >= 0

    def detach(self):
        self.detached = True

    def ask(self, **what):
        return {"busy": False} if what.get("status") else {"ok": True}


@pytest.fixture(autouse=True)
def nothing_left_held():
    yield
    lib.claims._give_back()


@pytest.fixture
def settings(tmp_path):
    return replace(lib.config.load_settings(env={"MASSIVE_API_KEY": "k", "TIINGO_API_KEY": "t"}, env_file=None),
                   db_path=tmp_path / "liminal.db")


@pytest.fixture
def runs(monkeypatch):
    made: dict[str, FakeAttachment] = {}

    def feed_run(name, db_path, log=print):
        made[name] = FakeAttachment(name)
        return made[name]
    monkeypatch.setattr(lib, "feed_run", feed_run)
    monkeypatch.setattr(lib, "history_due", lambda s: False)
    monkeypatch.setattr(lib, "feed_closed", lambda s, n: False)
    return made


def _fetcher(settings, monkeypatch):
    log: list[str] = []
    f = fetcher.Fetcher(settings, log.append)
    monkeypatch.setattr(f, "_spawn", lambda args: Namespace(args=args, poll=lambda: None))
    f.last_pass, f.next_due = time.monotonic(), NOW + timedelta(days=1)  # no standing pass in these
    return f, log


def _linux(path, pid: int = 4321):
    """The suite inside WSL on the same database (its processes cannot be looked up from here)."""
    return lib.claims.Claims.open(path, me="linux::Ubuntu", pid=pid, alive=lambda p, s: True)


def test_a_feed_the_other_installation_is_fetching_is_waited_for_and_never_started_here(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    store = lib.Store(settings.db_path, check_same_thread=False)
    linux = _linux(settings.db_path)
    try:
        linux.take("feed:massive", what="the massive feed's run")
        store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        r = store.request_put("SPCX", by="chart", now=NOW)
        f.tick(store, NOW)
        row = store.request_get(r["id"])
        assert row["state"] == "collecting" and row["detail"] == "waiting for massive (fetching on linux::Ubuntu)"
        assert runs == {} and f.feeds == {}  # not started here: its run would only have been refused
        assert lib.collector.priority_requests(store, NOW)["SPCX"]["at"] == NOW  # on the stack its run there reads
        for seconds in (2, 4, 6):  # however often it is looked at: pending, never "its run ended without it"
            f.tick(store, NOW + timedelta(seconds=seconds))
        row = store.request_get(r["id"])
        assert row["state"] == "collecting" and row["detail"] == "waiting for massive (fetching on linux::Ubuntu)" and runs == {}
        store.set_synced("massive", "SPCX", NOW + timedelta(seconds=8))  # the run there served it
        f.tick(store, NOW + timedelta(seconds=10))
        row = store.request_get(r["id"])
        assert row["state"] == "done" and row["detail"] == "served by massive" and f.active == {} and runs == {}
    finally:
        linux.close()
        store.close()


def test_when_its_run_there_ends_without_the_symbol_the_feed_is_run_here(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    store = lib.Store(settings.db_path, check_same_thread=False)
    linux = _linux(settings.db_path)
    try:
        theirs = linux.take("feed:massive")
        store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        r = store.request_put("SPCX", by="page", now=NOW)
        f.tick(store, NOW)
        assert runs == {} and f.active[r["id"]]["away"] == {"massive"}
        linux.release(theirs)  # its run there ended (a cap, a stop) before it reached the symbol
        f.tick(store, NOW + timedelta(seconds=2))
        assert "massive" in runs and store.request_get(r["id"])["state"] == "collecting"  # held here now
        assert f.active[r["id"]]["away"] == set()
        runs["massive"].lives = 0  # and when the run here ends without it too: failed, as before
        f.tick(store, NOW + timedelta(seconds=4))
        f.tick(store, NOW + timedelta(seconds=6))
        row = store.request_get(r["id"])
        assert row["state"] == "failed" and "massive: its run ended without it" in row["detail"]
    finally:
        linux.close()
        store.close()


def test_the_standing_pass_leaves_a_feed_the_other_installation_is_fetching(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    store = lib.Store(settings.db_path, check_same_thread=False)
    linux = _linux(settings.db_path)
    try:
        linux.take("feed:massive")  # no lock file says so: a lock file's process id means nothing across systems
        assert not lib.proc.run_holders(settings.db_path)
        out = f.standing_pass(store, NOW)
        assert "massive" in out["going"] and "massive" not in runs and "tiingo" in runs
        assert any("fetching already: massive" in m for m in log)
    finally:
        linux.close()
        store.close()


def test_the_fetcher_says_it_is_at_work_and_takes_back_only_what_a_fetcher_that_is_gone_left(settings, monkeypatch, runs):
    monkeypatch.setattr(fetcher, "TICK_SECONDS", 0.05)
    f, log = _fetcher(settings, monkeypatch)
    linux = _linux(settings.db_path, pid=77)
    with lib.Store(settings.db_path) as store:
        store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        dead = store.request_put("SPCX", by="cli")["id"]
        theirs = store.request_put("AAPL", by="cli")["id"]
        store.request_next()
        store.request_next()
        with store.conn:  # one left by a fetcher here that is no more; one the other installation's fetcher is collecting
            store.conn.execute("UPDATE fetch_requests SET pid=999999999, state='collecting' WHERE id=?", (dead,))
            store.conn.execute("UPDATE fetch_requests SET pid=77, instance='linux::Ubuntu', state='collecting' WHERE id=?", (theirs,))
    linux.take("process:linux::Ubuntu:77", what=fetcher.AT_WORK)
    stop = threading.Event()
    t = threading.Thread(target=f.run, args=(stop,), daemon=True)
    t.start()
    try:
        end = time.monotonic() + 10
        while "massive" not in runs and time.monotonic() < end:
            time.sleep(0.02)
        assert "massive" in runs and any("1 request(s) left by the fetcher before" in m for m in log)
        here = [h for h in linux.holders(lib.claims.PROCESS) if h.instance != "linux::Ubuntu"]
        assert [(h.pid, h.what) for h in here] == [(os.getpid(), fetcher.AT_WORK)]  # seen from the other side
        with lib.Store(settings.db_path) as store:
            assert store.request_get(theirs)["state"] == "collecting" and store.request_get(theirs)["pid"] == 77  # left to it
            assert store.request_get(dead)["state"] == "collecting" and store.request_get(dead)["pid"] == os.getpid()  # taken anew
    finally:
        stop.set()
        t.join(10)
        linux.close()
    assert not t.is_alive()
    assert [h for h in lib.claims.held(settings.db_path, lib.claims.PROCESS) if h.mine] == []  # its own given back at its end


def test_a_fetcher_that_is_offline_leaves_the_requests_to_one_that_can_serve_them(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    f.settings = replace(settings, offline=True)
    store = lib.Store(settings.db_path, check_same_thread=False)
    linux = _linux(settings.db_path, pid=77)
    try:
        store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        r = store.request_put("SPCX", by="chart", now=NOW)
        linux.take("process:linux::Ubuntu:77", what=fetcher.AT_WORK)  # a fetcher at work on the other side
        assert f.fetcher_elsewhere()
        f.tick(store, NOW)
        assert store.request_get(r["id"])["state"] == "waiting" and runs == {}  # not taken, so not refused
        linux.release("process:linux::Ubuntu:77")
        linux.take("process:linux::Ubuntu:77", what=fetcher.NOT_FETCHING)  # the other one offline too: nobody serves
        assert not f.fetcher_elsewhere()
        f.tick(store, NOW + timedelta(seconds=2))
        row = store.request_get(r["id"])
        assert row["state"] == "failed" and "offline" in row["detail"]  # said, as before
    finally:
        linux.close()
        store.close()
