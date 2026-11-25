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
# The installation that is not the one running these tests (inside WSL this one is linux::Ubuntu itself)
OTHER = "linux::Ubuntu" if lib.claims.os_name() == "windows" else "windows::NEPTUNE"


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


class Spawned:
    """A stand-in for the extras' or the auditors' process (fetcher._spawn): runs until told TERM (1.14.0: the
    fetcher's end tells it so, and kills it at its deadline)."""

    def __init__(self, args=None):
        self.args, self.code = args, None

    def poll(self):
        return self.code

    def send_signal(self, number):
        self.code = 0

    def kill(self):
        self.code = -9


def _fetcher(settings, monkeypatch):
    log: list[str] = []
    f = fetcher.Fetcher(settings, log.append)
    monkeypatch.setattr(f, "_spawn", lambda args, kind="": Spawned(args))
    f.by_event = False  # the stand-in hears SIGTERM's way (send_signal)
    f.last_pass, f.next_due = time.monotonic(), NOW + timedelta(days=1)  # no standing pass in these
    return f, log


def _other(path, pid: int = 4321):
    """The other installation on the same database: the suite inside WSL seen from Windows, Windows' seen from
    inside WSL (its processes cannot be looked up from here)."""
    return lib.claims.Claims.open(path, me=OTHER, pid=pid, alive=lambda p, s: True)


def test_a_feed_the_other_installation_is_fetching_is_waited_for_and_never_started_here(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    store = lib.Store(settings.db_path, check_same_thread=False)
    other = _other(settings.db_path)
    try:
        other.take("feed:massive", what="the massive feed's run")
        store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        r = store.request_put("SPCX", by="chart", now=NOW)
        f.tick(store, NOW)
        row = store.request_get(r["id"])
        assert row["state"] == "collecting" and row["detail"] == f"waiting for massive (fetching on {OTHER})"
        assert runs == {} and f.feeds == {}  # not started here: its run would only have been refused
        assert lib.collector.priority_requests(store, NOW)["SPCX"]["at"] == NOW  # on the stack its run there reads
        for seconds in (2, 4, 6):  # however often it is looked at: pending, never "its run ended without it"
            f.tick(store, NOW + timedelta(seconds=seconds))
        row = store.request_get(r["id"])
        assert row["state"] == "collecting" and row["detail"] == f"waiting for massive (fetching on {OTHER})" and runs == {}
        store.set_synced("massive", "SPCX", NOW + timedelta(seconds=8))  # the run there served it
        f.tick(store, NOW + timedelta(seconds=10))
        row = store.request_get(r["id"])
        assert row["state"] == "done" and row["detail"] == "served by massive" and f.active == {} and runs == {}
    finally:
        other.close()
        store.close()


def test_when_its_run_there_ends_without_the_symbol_the_feed_is_run_here(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    store = lib.Store(settings.db_path, check_same_thread=False)
    other = _other(settings.db_path)
    try:
        theirs = other.take("feed:massive")
        store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        r = store.request_put("SPCX", by="page", now=NOW)
        f.tick(store, NOW)
        assert runs == {} and f.active[r["id"]]["away"] == {"massive"}
        other.release(theirs)  # its run there ended (a cap, a stop) before it reached the symbol
        f.tick(store, NOW + timedelta(seconds=2))
        assert "massive" in runs and store.request_get(r["id"])["state"] == "collecting"  # held here now
        assert f.active[r["id"]]["away"] == set()
        runs["massive"].lives = 0  # and when the run here ends without it too: failed, as before
        f.tick(store, NOW + timedelta(seconds=4))
        f.tick(store, NOW + timedelta(seconds=6))
        row = store.request_get(r["id"])
        assert row["state"] == "failed" and "massive: its run ended without it" in row["detail"]
    finally:
        other.close()
        store.close()


def test_the_standing_pass_leaves_a_feed_the_other_installation_is_fetching(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    store = lib.Store(settings.db_path, check_same_thread=False)
    other = _other(settings.db_path)
    try:
        other.take("feed:massive")  # no lock file says so: a lock file's process id means nothing across systems
        assert not lib.proc.run_holders(settings.db_path)
        out = f.standing_pass(store, NOW)
        assert "massive" in out["going"] and "massive" not in runs and "tiingo" in runs
        assert any("fetching already: massive" in m for m in log)
    finally:
        other.close()
        store.close()


def test_the_fetcher_says_it_is_at_work_and_takes_back_only_what_a_fetcher_that_is_gone_left(settings, monkeypatch, runs):
    monkeypatch.setattr(fetcher, "TICK_SECONDS", 0.05)
    f, log = _fetcher(settings, monkeypatch)
    other = _other(settings.db_path, pid=77)
    with lib.Store(settings.db_path) as store:
        store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        dead = store.request_put("SPCX", by="cli")["id"]
        theirs = store.request_put("AAPL", by="cli")["id"]
        store.request_next()
        store.request_next()
        with store.conn:  # one left by a fetcher here that is no more; one the other installation's fetcher is collecting
            store.conn.execute("UPDATE fetch_requests SET pid=999999999, state='collecting' WHERE id=?", (dead,))
            store.conn.execute("UPDATE fetch_requests SET pid=77, instance=?, state='collecting' WHERE id=?", (OTHER, theirs))
    other.take(f"process:{OTHER}:77", what=fetcher.AT_WORK)
    stop = threading.Event()
    t = threading.Thread(target=f.run, args=(stop,), daemon=True)
    t.start()
    try:
        end = time.monotonic() + 10
        while "massive" not in runs and time.monotonic() < end:
            time.sleep(0.02)
        assert "massive" in runs and any("1 request(s) left by the fetcher before" in m for m in log)
        here = [h for h in other.holders(lib.claims.PROCESS) if h.instance != OTHER]
        assert [(h.pid, h.what) for h in here] == [(os.getpid(), fetcher.AT_WORK)]  # seen from the other side
        with lib.Store(settings.db_path) as store:
            # the feed's run is held first and the request written as collecting right after: waited for, not read
            # the moment the run shows (on a busy machine it still said "assessing")
            while (store.request_get(dead)["state"], store.request_get(dead)["pid"]) != ("collecting", os.getpid()) \
                    and time.monotonic() < end:
                time.sleep(0.02)
            assert store.request_get(theirs)["state"] == "collecting" and store.request_get(theirs)["pid"] == 77  # left to it
            assert store.request_get(dead)["state"] == "collecting" and store.request_get(dead)["pid"] == os.getpid()  # taken anew
    finally:
        stop.set()
        t.join(10)
        other.close()
    assert not t.is_alive()
    assert [h for h in lib.claims.held(settings.db_path, lib.claims.PROCESS) if h.mine] == []  # its own given back at its end


def test_a_fetcher_that_is_offline_leaves_the_requests_to_one_that_can_serve_them(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    f.settings = replace(settings, offline=True)
    store = lib.Store(settings.db_path, check_same_thread=False)
    other = _other(settings.db_path, pid=77)
    try:
        store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        r = store.request_put("SPCX", by="chart", now=NOW)
        other.take(f"process:{OTHER}:77", what=fetcher.AT_WORK)  # a fetcher at work on the other side
        assert f.fetcher_elsewhere()
        f.tick(store, NOW)
        assert store.request_get(r["id"])["state"] == "waiting" and runs == {}  # not taken, so not refused
        other.release(f"process:{OTHER}:77")
        other.take(f"process:{OTHER}:77", what=fetcher.NOT_FETCHING)  # the other one offline too: nobody serves
        assert not f.fetcher_elsewhere()
        f.tick(store, NOW + timedelta(seconds=2))
        row = store.request_get(r["id"])
        assert row["state"] == "failed" and "offline" in row["detail"]  # said, as before
    finally:
        other.close()
        store.close()


def test_a_fetcher_that_reads_only_writes_nothing(settings, monkeypatch, runs):
    """LIMINAL_READONLY, as the suite inside WSL first comes in on Windows' database: until then a fetcher that
    "read only" still wrote its status, took back the requests of a fetcher before it, and marked the waiting ones
    failed. Now nothing of it reaches the file: a request is the other fetcher's to take, and the status in the
    file is that fetcher's own."""
    from liminal_libs.storage import common

    with lib.Store(settings.db_path) as made:  # the database as the fetcher that writes there left it
        made.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        r = made.request_put("SPCX", by="chart", now=NOW)
        lib.write_status(made, {"busy": False, "by": "the fetcher that writes"})
    monkeypatch.setattr(common, "_READ_ONLY", [True])  # (the integrator's command line sets it: cli.main)
    monkeypatch.setattr(fetcher, "TICK_SECONDS", 0.01)
    f, log = _fetcher(settings, monkeypatch)
    f.settings = replace(settings, read_only=True)
    monkeypatch.setattr(lib.Store, "request_reset", lambda self: pytest.fail("a reset is a write"))
    stop, changes, tick = threading.Event(), [], f.tick

    def once(store, now):
        tick(store, now)
        assert store.conn.execute("PRAGMA query_only").fetchone() == (1,)  # sealed: it could not write if it tried
        changes.append(store.conn.total_changes)
        stop.set()
        f.wake.set()

    monkeypatch.setattr(f, "tick", once)
    f.run(stop)
    assert changes == [0] and runs == {} and not [line for line in log if "Error" in line or "readonly" in line]
    monkeypatch.setattr(common, "_READ_ONLY", [False])
    with lib.Store(settings.db_path) as after:
        assert after.request_get(r["id"])["state"] == "waiting"  # left to a fetcher that can serve it
        assert lib.read_status(after) == {"busy": False, "by": "the fetcher that writes"}
    assert lib.claims.held(settings.db_path) == []  # nor is it "at work here" for the other side


def test_the_command_line_seals_a_process_that_reads_only_and_says_a_database_that_is_behind(monkeypatch, capsys):
    from liminal_integrator import cli
    from liminal_libs.storage import common

    monkeypatch.setattr(common, "_READ_ONLY", [False])
    seen: dict = {}

    def serve(args, settings):
        seen["sealed"] = common.read_only()
        if seen.get("behind"):
            raise lib.Behind("X:/data/liminal.db is on another system's drive and behind this software (no table claims)")
        return 0

    monkeypatch.setattr(cli, "apply_instance", lambda args: None)
    monkeypatch.setattr(cli, "build_parser", lambda: Namespace(parse_args=lambda argv: Namespace(func=serve)))
    monkeypatch.setattr(lib.config, "load_settings", lambda **kw: Namespace(read_only=True))
    assert cli.main(["serve"]) == 0 and seen["sealed"] is True
    seen["behind"] = True
    assert cli.main(["serve"]) == 2  # said in words, no traceback: it is the other system's to bring up to date
    assert "behind this software (no table claims)" in capsys.readouterr().err

    def unreachable(**kw):
        raise lib.LinkError("the helper on Windows did not answer (pythonw.exe -m liminal_libs.storage.link)")

    monkeypatch.setattr(lib.config, "load_settings", unreachable)  # (the settings are asked of the helper first)
    assert cli.main(["serve"]) == 2 and "the helper on Windows did not answer" in capsys.readouterr().err


def test_a_feed_run_started_by_hand_here_is_waited_for_not_failed(settings, monkeypatch, runs):
    """The review of 2026-11-21, item 26: a feed run by hand on this installation (`--source massive sync`) holds
    the feed's claim; a request for it started a run here that was refused and ended, and the request failed with
    "its run ended without it". It is waited for like the other installation's run; when it ends, held here."""
    f, log = _fetcher(settings, monkeypatch)
    store = lib.Store(settings.db_path, check_same_thread=False)
    by_hand = lib.claims.Claims.open(settings.db_path, pid=os.getppid())  # this installation, another live process
    try:
        claim = by_hand.take("feed:massive", what="the massive feed's run")
        store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        r = store.request_put("SPCX", by="cli", now=NOW)
        f.tick(store, NOW)
        for seconds in (2, 4):
            f.tick(store, NOW + timedelta(seconds=seconds))
        row = store.request_get(r["id"])
        assert row["state"] == "collecting" and row["detail"] == f"waiting for massive (fetching in process {os.getppid()})"
        assert runs == {}  # not started here: the claim would only have refused it
        by_hand.release(claim)  # the run by hand ended before it reached the symbol
        f.tick(store, NOW + timedelta(seconds=6))
        assert "massive" in runs and store.request_get(r["id"])["state"] == "collecting"
    finally:
        by_hand.close()
        store.close()
