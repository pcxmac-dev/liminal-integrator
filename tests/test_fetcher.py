"""The fetcher (fetcher.py): a stack of requests in front, the plugins behind. It assesses the work
for a symbol over the plugins set up here and holds the runs of the feeds that deliver it; its
standing pass runs once new data can exist. No process starts here: the feeds' runs are fakes."""
from __future__ import annotations

import json
import threading
import time
from argparse import Namespace
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from liminal_integrator import cli, fetcher, lib

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)  # a Tuesday, 10:00 ET: the session is on


class FakeAttachment:
    def __init__(self, name, lives=999):
        self.name, self.lives, self.detached, self.host_pid = name, lives, False, 4242
        self.asked: list[dict] = []

    def alive(self):
        if self.detached:
            return False
        self.lives -= 1
        return self.lives >= 0

    def detach(self):
        self.detached = True

    def ask(self, **what):
        self.asked.append(what)
        return {"busy": False} if what.get("status") else {"ok": True}


@pytest.fixture
def settings(tmp_path):
    return replace(lib.config.load_settings(env={"MASSIVE_API_KEY": "k", "TIINGO_API_KEY": "t"}, env_file=None),
                   db_path=tmp_path / "liminal.db")


@pytest.fixture
def runs(monkeypatch):
    """The feeds' runs as the fetcher holds them (lib.feed_run): fakes, by feed."""
    made: dict[str, FakeAttachment] = {}

    def feed_run(name, db_path, log=print):
        made[name] = FakeAttachment(name)
        return made[name]
    monkeypatch.setattr(lib, "feed_run", feed_run)
    monkeypatch.setattr(lib, "history_due", lambda s: False)
    monkeypatch.setattr(lib, "feed_closed", lambda s, n: False)
    monkeypatch.setattr(lib.proc, "run_holders", lambda p: {})
    return made


def _fetcher(settings, monkeypatch):
    log: list[str] = []
    f = fetcher.Fetcher(settings, log.append)
    monkeypatch.setattr(f, "_spawn", lambda args: Namespace(args=args, poll=lambda: None))
    return f, log


# -- assessing a symbol ------------------------------------------------------------------------
def test_assessing_a_symbol_plans_each_era_to_the_feed_that_delivers_it(settings):
    with lib.Store(settings.db_path) as store:
        for feed in ("massive", "tiingo"):
            store.watch(feed, ["SPCX"], "minute", exchange="XNAS")
        a = fetcher.assess(store, settings, "spcx", now=NOW)
    assert a.symbol == "SPCX" and a.asset == "stock" and a.note == ""
    assert a.jobs and a.feeds and set(a.feeds) <= {"massive", "tiingo"}
    assert all(j["plugin"] in ("massive", "tiingo") and j["resolution"] in ("day", "minute", "second") for j in a.jobs)
    order = [("day", "minute", "second").index(j["resolution"]) for j in a.jobs]
    assert order == sorted(order)  # the user's order: days, then minutes, then seconds
    assert {o["plugin"] for o in a.offers} == {"massive", "tiingo"}
    assert all({"resolution", "since", "latency", "requests", "capacity"} <= set(o) for o in a.offers)
    assert any(j["plugin"] == "tiingo" and j["resolution"] == "day" and j["unique"] for j in a.jobs)  # Tiingo's 1962 days: its alone
    assert json.loads(json.dumps(a.as_dict()))["feeds"] == a.feeds and a.live == []  # live not asked for
    # live asked for too: what can serve its current session, the freshest first (a stream, else requests)
    with lib.Store(settings.db_path) as store:
        live = fetcher.assess(store, settings, "SPCX", kinds=("bars", "live"), now=NOW).live
    assert live and all(plugin in ("massive", "tiingo") and what for plugin, what in live)


def test_a_symbol_nobody_watches_goes_on_the_feeds_that_can_collect_it_first(settings):
    with lib.Store(settings.db_path) as store:
        a = fetcher.assess(store, settings, "MSFT", now=NOW)
        assert a.asset == "stock" and a.feeds
        assert {w["source"] for w in store.watchlist(ticker="MSFT")} == {"massive", "tiingo"}
        no_futures = replace(lib.config.load_settings(env={"TIINGO_API_KEY": "t"}, env_file=None), db_path=settings.db_path)
        none = fetcher.assess(store, no_futures, "NQ1!", now=NOW)  # no feed set up here collects futures (Massive would)
        assert none.feeds == [] and none.note == "no feed set up here collects it" and store.watchlist(ticker="NQ1!") == []


def test_a_symbol_is_assessed_under_its_stored_ticker_however_it_is_typed(settings):
    with lib.Store(settings.db_path) as store:
        store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        for typed in ("nasdaq:spcx", "SPCX::NASDAQ", " spcx "):
            a = fetcher.assess(store, settings, typed, now=NOW)
            assert a.symbol == "SPCX" and a.asset == "stock" and a.feeds  # its row, not a second one under the typed text
        assert [w["ticker"] for w in store.watchlist(ticker="SPCX")] == ["SPCX"]
        assert store.watchlist(ticker="SPCX::NASDAQ") == [] and store.watchlist(ticker="NASDAQ:SPCX") == []
        fx = fetcher.assess(store, settings, "EUR/USD", now=NOW)
        assert fx.symbol == "EURUSD" and fx.asset == "fx" and store.watchlist(ticker="EURUSD")


def test_a_listing_abroad_goes_to_the_feeds_carrying_its_exchange_and_to_none_otherwise(settings, monkeypatch):
    known = lib.providers()
    monkeypatch.setitem(known, "tiingo", known["tiingo"].with_(exchanges=frozenset({"US", "XSHG", "XSHE"})))
    with lib.Store(settings.db_path) as store:
        a = fetcher.assess(store, settings, "600519.SS", now=NOW)  # Shanghai: Tiingo carries it, Massive does not
        assert a.symbol == "600519.SS" and a.asset == "stock" and a.feeds == ["tiingo"] and a.note == ""
        assert [(j["plugin"], j["resolution"], j["end"], j["unique"]) for j in a.jobs] == [("tiingo", "day", None, True)]  # one job, not the US market's eras
        assert {w["source"] for w in store.watchlist(ticker="600519.SS")} == {"tiingo"}
        assert store.watchlist(ticker="600519.SS")[0]["exchange"] == "XSHG"
        none = fetcher.assess(store, settings, "TSE:7203", now=NOW)  # Tokyo: no feed set up here
        assert none.symbol == "7203.T" and none.feeds == [] and none.note == "no feed set up here carries XTKS listings"
        assert store.watchlist(ticker="7203.T") == []


def test_next_due_is_the_earliest_moment_a_feed_can_have_new_data(settings):
    profiles = {n: p for n, p in lib.feed_profiles(settings).items() if p.assets}
    due = fetcher.next_due(settings, profiles, NOW)
    assert due is not None and due > NOW  # on a Tuesday morning the next session's data is still to come
    assert fetcher.next_due(settings, {}, NOW) is None
    # a feed's listings abroad count by their exchanges' days: Thanksgiving, 10:00 ET, the US closed, Tokyo trading
    thanksgiving = datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc)
    stocks = {n: replace(p, assets={"stock"}) for n, p in profiles.items() if "stock" in p.assets}  # (fx and crypto: always on)
    us = fetcher.next_due(settings, stocks, thanksgiving)
    abroad = fetcher.next_due(settings, stocks, thanksgiving, {"tiingo": {"XTKS"}})
    assert us is not None and thanksgiving < abroad < us  # Tokyo's Thursday is due before the US Friday


# -- requests --------------------------------------------------------------------------------
def test_a_request_is_assessed_collected_on_its_feeds_runs_and_done_once_served(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    f.last_pass, f.next_due = time.monotonic(), NOW + timedelta(days=1)  # no standing pass here
    store = lib.Store(settings.db_path, check_same_thread=False)
    for feed in ("massive", "tiingo"):
        store.watch(feed, ["SPCX"], "minute", exchange="XNAS")
    r = store.request_put("SPCX", by="chart", now=NOW)
    f.tick(store, NOW)
    row = store.request_get(r["id"])
    assert row["state"] == "collecting" and set(row["plan"]["feeds"]) == set(f.feeds) == set(runs)
    assert "massive" in row["detail"] and "tiingo" in row["detail"]  # on its runs, waiting for them
    assert lib.collector.priority_requests(store, NOW)["SPCX"]["at"] == NOW
    st = f.status()
    assert st["busy"] and st["active"][0]["symbol"] == "SPCX" and st["feeds"] == sorted(runs)
    assert any("asked for it first" in m for m in log)
    f.tick(store, NOW + timedelta(seconds=2))
    assert store.request_get(r["id"])["state"] == "collecting"  # nothing served yet: waiting
    assert "waiting for" in store.request_get(r["id"])["detail"]
    for feed in row["plan"]["feeds"]:
        store.set_synced(feed, "SPCX", NOW + timedelta(seconds=5))
    f.tick(store, NOW + timedelta(seconds=10))
    row = store.request_get(r["id"])
    assert row["state"] == "done" and row["detail"].startswith("served by") and f.active == {}
    assert all(a.detached for a in runs.values()) and f.feeds == {}  # held for nobody any more: let go
    assert lib.read_status(store)["busy"] is False
    store.close()


def test_a_request_fails_when_its_feeds_runs_end_without_serving_it(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    f.last_pass, f.next_due = time.monotonic(), NOW + timedelta(days=1)
    store = lib.Store(settings.db_path, check_same_thread=False)
    store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
    r = store.request_put("SPCX", by="page", now=NOW)
    f.tick(store, NOW)
    runs["massive"].lives = 0  # its run ended (a cap, a refusal) before serving it
    f.tick(store, NOW + timedelta(seconds=2))
    f.tick(store, NOW + timedelta(seconds=4))
    row = store.request_get(r["id"])
    assert row["state"] == "failed" and "massive: its run ended without it" in row["detail"]
    # a symbol no feed here collects fails at once, with the reason
    r2 = store.request_put("NQ1!", by="page", now=NOW)
    f.settings = replace(lib.config.load_settings(env={"TIINGO_API_KEY": "t"}, env_file=None), db_path=settings.db_path)
    f.tick(store, NOW + timedelta(seconds=6))
    assert store.request_get(r2["id"])["state"] == "failed" and "no feed set up here" in store.request_get(r2["id"])["detail"]
    store.close()


def test_a_cancelled_request_is_dropped_and_one_asked_anew_asks_the_feeds_again(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    f.last_pass, f.next_due = time.monotonic(), NOW + timedelta(days=1)
    store = lib.Store(settings.db_path, check_same_thread=False)
    store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
    r = store.request_put("SPCX", by="chart", now=NOW)
    f.tick(store, NOW)
    assert r["id"] in f.active
    later = NOW + timedelta(minutes=5)
    store.request_put("SPCX", by="page", now=later)  # asked anew while collecting: asked of the feeds from now
    f.tick(store, later)
    assert lib.collector.priority_requests(store, later)["SPCX"]["at"] == later and f.active[r["id"]]["asked"] == later
    store.request_cancel(r["id"])
    f.tick(store, later + timedelta(seconds=2))
    assert f.active == {} and store.request_get(r["id"])["state"] == "cancelled"
    store.close()


def test_halted_the_requests_wait_and_offline_they_fail(settings, monkeypatch, runs):
    f, log = _fetcher(settings, monkeypatch)
    f.last_pass, f.next_due = time.monotonic(), NOW + timedelta(days=1)
    store = lib.Store(settings.db_path, check_same_thread=False)
    store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
    r = store.request_put("SPCX", by="chart", now=NOW)
    lib.collector.set_pause(store, True, NOW, halt=True)
    f.tick(store, NOW)
    assert store.request_get(r["id"])["state"] == "waiting" and runs == {}
    lib.collector.set_pause(store, False, NOW)
    f.settings = replace(settings, offline=True)
    f.tick(store, NOW)
    row = store.request_get(r["id"])
    assert row["state"] == "failed" and "offline" in row["detail"] and "it would ask massive" in row["detail"]
    assert row["plan"]["feeds"] == ["massive"] and runs == {}  # assessed, so the page shows the plan; nothing asked
    r2 = store.request_put("TSE:7203", by="page", now=NOW)
    f.tick(store, NOW + timedelta(seconds=1))
    assert "no feed set up here carries XTKS listings" in store.request_get(r2["id"])["detail"]
    store.close()


# -- the standing pass -----------------------------------------------------------------------
def test_the_standing_pass_holds_every_feed_and_waits_for_new_data(settings, monkeypatch, runs):
    monkeypatch.setattr(lib, "history_due", lambda s: True)
    monkeypatch.setattr(lib, "history_run", lambda db, log=print: FakeAttachment("history"))
    monkeypatch.setattr(lib, "feed_closed", lambda s, n: n == "tiingo")  # a closed archive: not run
    f, log = _fetcher(settings, monkeypatch)
    spawned: list[list[str]] = []
    monkeypatch.setattr(f, "_spawn", lambda args: spawned.append(args) or Namespace(poll=lambda: None))
    set_up = {n for n, p in lib.feed_profiles(settings).items() if p.assets}  # with keys, or keyless (the crypto exchanges)
    store = lib.Store(settings.db_path, check_same_thread=False)
    assert f.pass_due(store, NOW)  # never run
    f.tick(store, NOW)
    assert set(runs) == set_up - {"tiingo"} and f.by_pass == set(runs) and f.history is not None
    assert "massive" in runs and "tiingo" not in runs
    assert spawned[-1][1:] == ["-m", "liminal_app", "sync", "--extras-only"]  # the app's module (host.APP_MODULE)
    assert f.next_due is not None and f.next_due > NOW and f.last_pass_at == NOW
    assert any("pass: " in m and "massive" in m and " held" in m and "nothing new before" in m for m in log)
    assert not f.pass_due(store, NOW + timedelta(minutes=5))  # within the hour: not again
    monkeypatch.setattr(fetcher, "pass_hours", lambda: 0.0)
    assert not f.pass_due(store, NOW)  # the hour over, but nothing new can exist before next_due
    assert f.pass_due(store, f.next_due)  # new data can exist now
    run_id = store.start_run("massive", "sync")
    store.finish_run(run_id, 10, 0, "stopped", "request cap reached")
    assert f.pass_due(store, NOW)  # a run stopped short: more to do
    f.ask_pass()
    assert f.pass_asked and f.wake.is_set()
    st = f.status()
    assert st["passFeeds"] == sorted(runs) and st["history"] is True and st["busy"] and st["passHours"] == 0.0
    f.tick(store, NOW + timedelta(seconds=1))  # the pass asked for: the runs held already go on, held
    assert not f.pass_asked and not runs["massive"].detached
    f.let_go()
    assert all(a.detached for a in runs.values()) and f.feeds == {} and f.by_pass == set() and f.history is None
    # paused: no pass
    lib.collector.set_pause(store, True, NOW, minutes=30)
    assert f.standing_pass(store, NOW)["why"] == "paused"
    store.close()


def test_the_standing_pass_leaves_a_feed_fetching_elsewhere_alone_and_says_which_are_not_set_up(tmp_path, monkeypatch, runs):
    settings = replace(lib.config.load_settings(env={}, env_file=None), db_path=tmp_path / "liminal.db")  # no Massive key
    monkeypatch.setattr(lib.proc, "run_holders", lambda p: {"coinbase": 99})  # Coinbase's run, in another process
    f, log = _fetcher(settings, monkeypatch)
    store = lib.Store(settings.db_path, check_same_thread=False)
    out = f.standing_pass(store, NOW)
    assert "massive" in out["unset"] and "coinbase" in out["going"] and "coinbase" not in runs and "massive" not in runs
    assert "bitstamp" in runs  # keyless: set up by default
    assert any("fetching already: coinbase" in m and "not set up here: " in m and "massive" in m for m in log)
    monkeypatch.setattr(lib.proc, "run_holders", lambda p: {None: 99})  # the whole database locked (its data being moved)
    assert f.standing_pass(store, NOW)["why"] == "the whole database is locked"
    store.close()


def test_the_fetcher_answers_its_clients_and_runs_until_its_host_stops_it(settings, monkeypatch, runs):
    monkeypatch.setattr(fetcher, "TICK_SECONDS", 0.05)
    f, log = _fetcher(settings, monkeypatch)
    assert f.handle({"ask": True, "status": True})["pid"] and f.handle({"ask": True, "wake": True}) == {"ok": True}
    assert f.handle({"ask": True, "pass": True}) == {"ok": True} and f.pass_asked
    assert "error" in f.handle({"ask": True, "what": "else"})
    with lib.Store(settings.db_path) as store:
        store.watch("massive", ["SPCX"], "minute", exchange="XNAS")
        r = store.request_put("SPCX", by="cli")
        store.request_next()  # left assessing by a fetcher that died: waiting again at the start
    stop = threading.Event()
    t = threading.Thread(target=f.run, args=(stop,), daemon=True)
    t.start()
    end = time.monotonic() + 5
    while "massive" not in runs and time.monotonic() < end:
        time.sleep(0.02)
    assert "massive" in runs and any("waiting again" in m for m in log)
    stop.set()
    t.join(5)
    assert not t.is_alive() and runs["massive"].detached  # let go at the end
    with lib.Store(settings.db_path) as store:
        assert store.request_get(r["id"])["state"] == "collecting"  # its run let go; taken up by the next fetcher
        assert lib.read_status(store)["feeds"] == []


def test_run_host_serves_the_fetcher_with_the_apps_page(settings, monkeypatch):
    seen: dict = {}

    def serve_fetcher(s, f, h, port, rescan=True, reload_settings=None):
        seen.update(f=f, h=h, port=port, rescan=rescan)
        return "ended"
    monkeypatch.setattr(lib, "page", lambda: serve_fetcher)
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "none")
    monkeypatch.setenv("LIMINAL_NO_RESCAN", "1")
    assert fetcher.run_host(settings, lambda m: None) == "ended"
    assert isinstance(seen["f"], fetcher.Fetcher) and seen["h"].name == "fetcher" and seen["port"] is None
    assert seen["rescan"] is False
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "8790")
    assert fetcher.page_port() == 8790
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "0")
    assert fetcher.page_port() == 0  # a free one
    assert fetcher.run_host(settings, lambda m: None, port=0, rescan=True) == "ended" and seen["port"] == 0 and seen["rescan"]


# -- the command line ------------------------------------------------------------------------
def test_the_command_line(settings, monkeypatch, capsys):
    monkeypatch.setattr(lib.config, "load_settings", lambda *a, **kw: settings)
    assert cli.main(["status"]) == 0 and "never run" in capsys.readouterr().out
    assert cli.main(["request"]) == 2  # which symbols?
    assert cli.main(["request", "aapl", "nq1!", "--kinds", "bars,live"]) == 1  # no fetcher answers: they wait on the stack
    out = capsys.readouterr().out
    assert cli.main(["request", "twse:2330", "eur/usd"]) == 1 and "2330.TW" in capsys.readouterr().out  # under the stored names
    with lib.Store(settings.db_path) as store:
        assert {r["symbol"] for r in store.request_rows()} >= {"AAPL", "NQ1!", "2330.TW", "EURUSD"}
    assert "#1 AAPL: waiting (bars,live)" in out and "#2 NQ1!: waiting" in out and "wait on its stack" in out
    assert cli.main(["cancel", "--id", "1"]) == 0 and cli.main(["cancel", "--id", "1"]) == 1
    assert cli.main(["fetcher", "status", "--limit", "5"]) == 0
    out = capsys.readouterr().out
    assert "NQ1!" in out and "cancelled" in out
    held = FakeAttachment("fetcher")
    monkeypatch.setattr(lib, "attach_fetcher", lambda db, log=print: held)
    monkeypatch.setattr(lib, "wait_for_fetcher", lambda h, log, every=2.0: None)
    assert cli.main(["pass"]) == 0 and held.asked == [{"pass": True}] and held.detached
    seen = []
    monkeypatch.setattr(fetcher, "run_host", lambda s, log=None, port=None, rescan=None: seen.append(s) or "ended")
    assert cli.main(["host"]) == 0 and seen == [settings]
    args = cli.build_parser().parse_args(["service"])
    assert args.action == "status"
