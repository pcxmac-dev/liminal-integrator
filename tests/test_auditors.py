"""The integrator's auditors (auditors.py, 1.13.0): what their page reads and asks, the auditors' process's work, and
the fetcher starting that process when an audit is asked for or the sweep is due. No process starts here: the
fetcher's spawn is a stand-in, and the work is called as the process would call it."""
from __future__ import annotations

import json
from argparse import Namespace
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from liminal_integrator import auditors, cli, fetcher, lib
from liminal_integrator.app import IntegratorApp
from liminal_libs.coverage import day_start_ms
from liminal_libs.storage import pulls

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)
DAY = 86_400_000
MON, TUE, WED, THU, FRI = (day_start_ms(date(2026, 10, d)) for d in (12, 13, 14, 15, 16))
SAT = day_start_ms(date(2026, 10, 17))


def _minute(day_ms: int) -> dict:
    return {"t": day_ms + 10 * 3_600_000, "o": 10.0, "h": 11.0, "l": 9.0, "c": 10.0, "v": 100, "vw": 10.0, "n": 5}


def _daily(day_ms: int) -> dict:
    return {"t": day_ms, "o": 10.0, "h": 11.0, "l": 9.0, "c": 10.0, "v": 5000, "vw": 10.0, "n": 50}


@pytest.fixture
def settings(tmp_path):
    return replace(lib.config.load_settings(env={"MASSIVE_API_KEY": "k"}, env_file=None), db_path=tmp_path / "liminal.db")


@pytest.fixture(autouse=True)
def the_defaults():
    lib.auditing.set_policy(None)
    yield
    lib.auditing.set_policy(None)
    lib.set_read_only(False)


def _with_a_hole(settings, ticker="AAA") -> None:
    """A watched series whose Wednesday has no minute bar though its daily bar shows it traded."""
    with lib.Store(settings.db_path) as store:
        store.watch("massive", [ticker], "minute")
        store.upsert_bars("massive", ticker, "minute", 1, [_minute(d) for d in (MON, TUE, THU, FRI)])
        store.upsert_bars("massive", ticker, "day", 1, [_daily(d) for d in (MON, TUE, WED, THU, FRI)])
        store.add_coverage("massive", ticker, "minute", MON, SAT)
        store.add_coverage("massive", ticker, "day", MON, SAT)


def _app(settings, log=None) -> IntegratorApp:
    return IntegratorApp(log=(log.append if log is not None else lambda *_: None), db_path=settings.db_path)


# -- the page ------------------------------------------------------------------------------------------------------------
def test_the_page_reads_where_the_auditors_stand(settings):
    _with_a_hole(settings)
    got = auditors.overview(_app(settings))
    assert got["plugin"] is None and got["problem"] == "" and got["running"] is False and got["asked"] == []
    assert got["policy"] == lib.auditing.Policy().as_dict()  # no plugin installed: the defaults
    assert got["sweep"]["last"] is None and got["sweep"]["due"] is True and got["findings"]["latest"] == []
    assert got["cache"]["folder"].endswith("cache") and got["cache"]["unverifiedBytes"] == 0
    json.dumps(got)
    app = _app(settings)
    assert app.api(None, "GET", "/api/auditor", {}, None) == (200, auditors.overview(app))


def test_the_page_asks_for_an_audit_or_a_sweep_and_it_goes_on_the_fetchers_stack(settings):
    log: list[str] = []
    app = _app(settings, log)
    status, got = app.api(None, "POST", "/api/auditor/run", {}, {"what": "sweep"})
    assert status == 200 and got["ok"] and got["said"] == "Asked: a sweep now, from where the last one stopped."
    cache = auditors.ask(app, {"what": "audit"})
    symbol = auditors.ask(app, {"what": "audit", "symbol": " aaa "})
    assert cache["said"] == "Asked: what waits in the fetch cache audited now." and "AAA's series gone over now" in symbol["said"]
    with lib.Store(settings.db_path) as store:
        rows = {r["symbol"]: r for r in store.requests_open()}
    assert set(rows) == {"*", "*CACHE", "AAA"} and all(r["kinds"] == ("audit",) and r["by"] == "page" for r in rows.values())
    assert [a["symbol"] for a in auditors.overview(app)["asked"]] and len(log) == 3
    for body in ({"what": "everything"}, {}, {"what": "audit", "symbol": "*"}, {"what": "audit", "symbol": "x" * 40}):
        with pytest.raises(lib.Refused):
            auditors.ask(app, body)


def test_a_copy_that_reads_only_asks_nothing_of_the_auditors(settings):
    app = _app(settings)
    with lib.Store(settings.db_path):  # (the file is there: a copy that reads only makes none)
        pass
    lib.set_read_only(True)
    with pytest.raises(lib.Refused) as refused:
        app.api(None, "POST", "/api/auditor/run", {}, {"what": "sweep"})
    assert refused.value.status == 409 and "reads only" in refused.value.reason
    lib.set_read_only(False)
    with lib.Store(settings.db_path) as store:
        assert store.requests_open() == []


# -- the auditors' process's work ------------------------------------------------------------------------------------------
def test_a_run_goes_over_what_was_asked_and_settles_the_asks(settings):
    _with_a_hole(settings)
    app = _app(settings)
    auditors.ask(app, {"what": "audit", "symbol": "AAA"})
    auditors.ask(app, {"what": "audit", "symbol": "NOPE"})
    said: list[str] = []
    out = auditors.run(settings, said.append)
    assert out["symbols"]["series"] == 1 and out["symbols"]["holes"] == 1 and out["symbols"]["only"] == ["massive:AAA"]
    assert "sweep" in out  # none ever ran: one was due
    with lib.Store(settings.db_path) as store:
        assert store.requests_open() == []
        done = store.request_rows(state="done")
        assert len(done) == 2 and all("asked: 1 series" in r["detail"] and "NOPE" in r["detail"] for r in done)
        (hole,) = store.findings(kind="hole")
        assert (hole["feed"], hole["ticker"], hole["start_ms"], hole["state"]) == ("massive", "AAA", WED, "open")
    assert said[-1].startswith("auditors: asked: 1 series") and "not watched by any feed: NOPE" in said[-1]
    got = auditors.overview(app)
    assert got["findings"]["open"] == 1 and got["sweep"]["last"]["series"] == 1 and got["sweep"]["due"] is False


def test_with_neither_a_sweep_due_nor_a_symbol_asked_a_run_audits_what_waits_in_the_cache(settings):
    _with_a_hole(settings)
    with lib.Store(settings.db_path) as store:
        store.kv_set(lib.auditing.LAST_KEY, json.dumps({"at": datetime.now(timezone.utc).isoformat(), "series": 0}))
        with pulls.pulling(store, "massive", "bars", ticker="AAA", asset="stock", timespan="minute") as p:
            store.upsert_bars("massive", "AAA", "minute", 1, [_minute(WED)])
    out = auditors.run(settings, lambda *_: None)
    assert out == {"cache": {"recovered": 0, "pulls": 1, "mismatch": 0, "removed": 0, "forgotten": 0}}
    with lib.Store(settings.db_path) as store:  # it passed: counted, and forgotten (the ledger is no history)
        assert store.pull(p.id) is None and store.cache_verified()["pulls"] == 1
    assert auditors.said(out) == ("cache: 1 pulls audited (0 with a finding), 0 left open by a run that is gone closed, "
                                  "0 files removed")
    assert auditors.said({}) == "nothing to do"


def test_a_sweep_asked_for_runs_though_none_is_due_and_a_copy_that_reads_only_audits_nothing(settings):
    _with_a_hole(settings)
    with lib.Store(settings.db_path) as store:
        store.kv_set(lib.auditing.LAST_KEY, json.dumps({"at": datetime.now(timezone.utc).isoformat(), "series": 0}))
        assert auditors.sweep_due(store, lib.auditing.Policy()) is False
        assert auditors.sweep_due(store, lib.auditing.Policy(), datetime.now(timezone.utc) + timedelta(hours=25)) is True
        assert auditors.sweep_due(store, lib.auditing.Policy(sweep_hours=None), NOW + timedelta(days=900)) is False
    assert auditors.run(settings, lambda *_: None, sweep=True)["sweep"]["series"] == 1
    said: list[str] = []
    assert auditors.run(replace(settings, read_only=True), said.append) == {"note": "reads only"}
    assert "reads only" in said[0]


def test_one_auditors_process_at_a_time_on_a_database_whichever_installation_started_it(settings):
    _with_a_hole(settings)
    # the installation that is not the one running these tests (inside WSL this one is linux::Ubuntu itself)
    other = "linux::Ubuntu" if lib.claims.os_name() == "windows" else "windows::NEPTUNE"
    theirs = lib.claims.Claims.open(settings.db_path, me=other, pid=4242, alive=lambda p, s: True)
    try:
        assert theirs.take(auditors.CLAIM, what="the auditors") is not None
        said: list[str] = []
        assert auditors.run(settings, said.append) == {"note": "at work already"} and "at work on this database" in said[0]
        assert auditors.overview(_app(settings))["running"] is True
        with lib.Store(settings.db_path) as store:
            assert store.findings() == []  # nothing was gone over from here meanwhile
    finally:
        theirs.close()


# -- the fetcher -----------------------------------------------------------------------------------------------------------
class Process:
    def __init__(self, args):
        self.args, self.ended = args, False

    def poll(self):
        return 0 if self.ended else None


def _fetcher(settings, monkeypatch):
    log: list[str] = []
    f = fetcher.Fetcher(settings, log.append)
    started: list[Process] = []
    monkeypatch.setattr(f, "_spawn", lambda args: started.append(Process(args)) or started[-1])
    return f, log, started


def test_an_audit_asked_for_is_handed_to_the_auditors_process_not_to_a_feeds_run(settings, monkeypatch):
    f, log, started = _fetcher(settings, monkeypatch)
    with lib.Store(settings.db_path) as store:
        store.kv_set(lib.auditing.LAST_KEY, json.dumps({"at": NOW.isoformat(), "series": 0}))  # (no sweep due)
        r = store.request_put("AAA", ("audit",), by="page")
        f.take_requests(store, NOW)
        assert store.request_get(r["id"])["state"] == "collecting" and f.active == {} and f.feeds == {}
        f.check_auditors(store, NOW)
        assert len(started) == 1 and started[0].args[-3:] == ["liminal_integrator", "audit", "run"]
        assert f.status()["auditors"] is True and "an audit asked for" in log[-1]
        f.check_auditors(store, NOW)
        assert len(started) == 1  # at work: not started twice
        # the process settles the ask and ends
        store.request_update(r["id"], state="done", detail="asked: 1 series")
        started[0].ended = True
        f.check_auditors(store, NOW)
        assert f.audit_asks == {} and len(started) == 1 and f.status()["auditors"] is False


def test_an_audit_its_process_ended_without_settling_is_failed_and_said(settings, monkeypatch):
    f, log, started = _fetcher(settings, monkeypatch)
    with lib.Store(settings.db_path) as store:
        store.kv_set(lib.auditing.LAST_KEY, json.dumps({"at": NOW.isoformat(), "series": 0}))
        r = store.request_put("*", ("audit",), by="page")
        f.take_requests(store, NOW)
        f.check_auditors(store, NOW)
        started[0].ended = True
        f.check_auditors(store, NOW)
        row = store.request_get(r["id"])
        assert (row["state"], row["detail"]) == ("failed", "the auditors ended before it") and len(started) == 1
        assert "the auditors ended before the audit asked for" in log[-1]


def test_the_sweep_is_started_when_it_is_due_and_looked_at_once_a_minute(settings, monkeypatch):
    f, log, started = _fetcher(settings, monkeypatch)
    clock = {"now": 1000.0}
    monkeypatch.setattr(fetcher.time, "monotonic", lambda: clock["now"])
    with lib.Store(settings.db_path) as store:
        f.check_auditors(store, NOW)  # none ever ran: due
        assert len(started) == 1 and "the sweep is due" in log[-1]
        started[0].ended = True
        store.kv_set(lib.auditing.LAST_KEY, json.dumps({"at": NOW.isoformat(), "series": 3}))
        f.check_auditors(store, NOW)
        assert len(started) == 1  # looked at a moment ago
        clock["now"] += fetcher.SWEEP_LOOK_S
        f.check_auditors(store, NOW + timedelta(hours=1))
        assert len(started) == 1  # looked at again: not due
        clock["now"] += fetcher.SWEEP_LOOK_S
        f.check_auditors(store, NOW + timedelta(hours=25))
        assert len(started) == 2


def test_a_fetcher_that_reads_only_starts_no_auditors(settings, monkeypatch):
    f, _, started = _fetcher(replace(settings, read_only=True), monkeypatch)
    with lib.Store(settings.db_path) as store:
        f.check_auditors(store, NOW)
    assert started == []


# -- the command line ------------------------------------------------------------------------------------------------------
def test_the_command_line_has_the_auditors(settings, capsys, monkeypatch):
    args = cli.build_parser().parse_args(["audit"])
    assert (args.action, args.symbols, args.func) == ("status", [], cli.cmd_audit)
    assert cli.build_parser().parse_args(["audit", "run", "AAA", "bbb"]).symbols == ["AAA", "bbb"]
    _with_a_hole(settings)
    monkeypatch.setattr(lib, "log_to", lambda db: (lambda *_: None))
    assert cli.cmd_audit(Namespace(action="sweep", symbols=[], limit=20), settings) == 0
    assert "sweep: 1 series" in capsys.readouterr().out
    assert cli.cmd_audit(Namespace(action="status", symbols=[], limit=20), settings) == 0
    out = capsys.readouterr().out
    assert "no plugin: the defaults" in out and "findings: 1 open" in out and "hole" in out and "massive:AAA" in out
    assert "audit on update on, sweep every 24.0 h for 10 min, on a mismatch repair, keep 0 days, cap 20 GB, 5 re-pulls" in out
