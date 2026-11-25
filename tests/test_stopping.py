"""The integrator's end in good order (1.14.0, Monday list item 38; the shutdown audit of 2026-11-24): the extras and
the auditors started through lifecycle.spawn, tied to the fetcher, told TERM when it lets go and killed at their
deadline; the fetcher a part of its app, its writes secured before the plugins end; the auditors stopping between
series; the service ending on its stop event and letting the fetcher go with a word. Nothing is started, signalled
or opened of this machine: the spawn, the processes, the events and the clock are stand-ins."""
from __future__ import annotations

import signal
import threading
import time
from dataclasses import replace

import pytest

from liminal_integrator import auditors, fetcher, lib, service
from liminal_integrator.app import IntegratorApp
from liminal_libs import lifecycle
from liminal_libs.lifecycle import StopEvent as RealStopEvent  # the class itself: conftest stands one in for tests


@pytest.fixture
def settings(tmp_path):
    return replace(lib.config.load_settings(env={"MASSIVE_API_KEY": "k"}, env_file=None), db_path=tmp_path / "liminal.db")


class Child:
    """A stand-in process: ends at TERM when it `heeds` it, only at KILL else; what it was sent, in order."""

    def __init__(self, heeds: bool = True):
        self.heeds, self.code, self.sent, self.pid = heeds, None, [], None

    def poll(self):
        return self.code

    def term(self):
        self.sent.append("TERM")
        if self.heeds:
            self.code = 0

    def send_signal(self, number):
        assert number == signal.SIGTERM
        self.term()

    def kill(self):
        self.sent.append("KILL")
        self.code = -9


class Event:
    def __init__(self, name):
        self.name, self.closed = name, False

    def close(self):
        self.closed = True


def _fetcher(settings, by_event: bool):
    log: list[str] = []
    f = fetcher.Fetcher(settings, log.append)
    started: list[dict] = []
    made: dict[str, Child] = {}
    heeds = {"extras": True, "auditors": False}  # the auditors ignore TERM: killed at the deadline

    def spawner(args, **kw):
        child = Child(heeds[kw["kind"]])
        started.append({"args": args, **kw})
        made[kw.get("env", {}).get(fetcher.STOP_VAR) or kw["kind"]] = child
        return child

    clock = lifecycle.FakeClock()
    f.spawner, f.by_event, f.clock, f.sleep = spawner, by_event, clock, clock.sleep
    f.make_event = Event
    f.set_event = lambda name: made[name].term() or True
    return f, log, started, clock


@pytest.mark.parametrize("by_event", [True, False], ids=["windows-stop-event", "sigterm"])
def test_the_extras_and_the_auditors_are_ended_when_the_fetcher_lets_go(settings, by_event):
    f, log, started, clock = _fetcher(settings, by_event)
    f.extras = f._spawn(["py", "-m", "liminal_charts", "sync", "--extras-only"], "extras")
    f.auditors = f._spawn(["py", "-m", "liminal_integrator", "audit", "run"], "auditors")
    extras, auditors_ = f.extras, f.auditors
    # started through lifecycle.spawn: the integrator's, tied to the fetcher, no output
    assert [(s["owner"], s["kind"], s["tied"]) for s in started] == [("integrator", "extras", True),
                                                                      ("integrator", "auditors", True)]
    if by_event:  # each with a stop event of its own, named in its environment
        names = [s["env"][fetcher.STOP_VAR] for s in started]
        assert len(set(names)) == 2 and all(n.startswith("Local\\liminal-stop-integrator-") for n in names)
    began = clock()
    f.let_go()
    assert extras.sent == ["TERM"]  # asked to stop, and it did
    assert auditors_.sent == ["TERM", "KILL"]  # it did not: killed at its deadline, not before
    assert clock() - began == pytest.approx(fetcher.CHILD_STOP_S, abs=0.2)
    assert f.extras is None and f.auditors is None and f.stop_events == {}
    assert "the extras terminated, the auditors killed" in log[-1]


def test_kill_ends_them_at_once_and_a_child_ended_already_is_left(settings):
    f, log, started, clock = _fetcher(settings, True)
    f.extras = f._spawn(["py"], "extras")
    f.auditors = f._spawn(["py"], "auditors")
    f.extras.code = 0  # ended by itself
    auditors_ = f.auditors
    began = clock()
    assert f.end_children(timeout=0) == {"extras": "gone", "auditors": "killed"}
    assert auditors_.sent == ["KILL"] and clock() == began


def test_the_fetcher_is_a_part_of_its_app_and_its_end_stops_the_app(settings, monkeypatch):
    """The fetcher host's end stops the integrator's app (its `secure`): the fetcher first, a part, then the plugins."""
    f = fetcher.Fetcher(settings, lambda *_: None)
    assert f.app.parts() == (f,)
    assert lifecycle.deliver(f, lifecycle.Signal.TERM, lifecycle.deadline_in(1))["how"] == "signalled"
    assert f.stop.is_set()
    seen: dict = {}

    class Host:
        def __init__(self, name, db_path, log=print):
            pass

        def serve(self, work, secure=None, handle=None):
            seen["secure"] = secure
            return "ended"

    monkeypatch.setattr(lib, "Host", Host)
    monkeypatch.setattr(IntegratorApp, "attach_plugins", lambda self, only=None: [])
    fetcher.run_host(settings, lambda *_: None, port=0)
    secure = seen["secure"]
    assert secure is not None and getattr(secure, "__func__", None) is lib.App.stop  # the app's stop
    app = secure.__self__
    secure()
    assert app.stopping and app.fetcher is not None


def test_signal_waits_for_the_runs_end_to_have_secured_its_writes(settings):
    f = fetcher.Fetcher(settings, lambda *_: None)
    order: list[str] = []
    f.running = True

    def end():  # the loop's end, at the moment the signal waits for it
        order.append("secured")
        f.running = False
        f.ended.set()

    real_wait = f.ended.wait

    def wait(timeout=None):
        order.append("waiting")
        end()
        return real_wait(timeout)

    f.ended.wait = wait
    got = f.signal(lifecycle.Signal.TERM, lifecycle.deadline_in(5))
    assert order == ["waiting", "secured"] and got["ended"] is True and f.stop.is_set()


def test_the_auditors_stop_between_series_and_leave_an_audit_asked_for_open(settings, monkeypatch):
    seen: list = []

    class Sweep:
        def __init__(self, store, **kw):
            pass

        def run(self, budget_s=None, only=None, stop=None):
            seen.append(stop)
            return {"series": 0, "days": 0, "pulls": 0, "holes": 0, "absent": 0, "closed": 0, "complete": False}

    monkeypatch.setattr(lib.auditing, "Sweep", Sweep)
    with lib.Store(settings.db_path) as store:
        store.watch("massive", ["AAA"], "minute")
        r = store.request_put("AAA", (lib.AUDIT,), by="page")
    stopped = lambda: True  # noqa: E731 - asked to stop at once
    out = auditors.run(settings, lambda *_: None, stop=stopped)
    assert seen == [stopped] and out["stopped"] is True and "sweep" not in out  # no sweep begun once asked to stop
    with lib.Store(settings.db_path) as store:
        assert store.request_get(r["id"])["state"] in lib.OPEN  # left for the next run


class K32:
    """A stand-in kernel32 for one event: set by the test."""

    def __init__(self):
        self.set, self.closed = False, False

    def CreateEventW(self, sa, manual, initial, name):
        return 7

    def WaitForSingleObject(self, handle, ms):
        return 0 if self.set else 0x102

    def CloseHandle(self, handle):
        self.closed = True
        return 1


def test_a_child_hears_its_stop_event_and_sigterm(monkeypatch):
    monkeypatch.setattr(lib.lifecycle, "StopEvent", RealStopEvent)  # with a stand-in kernel32
    old = {n: signal.getsignal(getattr(signal, n)) for n in ("SIGTERM", "SIGBREAK") if hasattr(signal, n)}
    try:
        k32 = K32()
        stop = fetcher.listen_for_stop(env={fetcher.STOP_VAR: "Local\\liminal-stop-integrator-extras-1-1"}, k32=k32,
                                       every=0.01)
        assert not stop.is_set()
        k32.set = True
        assert stop.wait(2) and _until(lambda: k32.closed)
        stop = fetcher.listen_for_stop(env={})
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)  # its handler, as the system would call it
        assert stop.is_set()
    finally:
        for n, was in old.items():
            signal.signal(getattr(signal, n), was)


def _until(cond, seconds: float = 2.0) -> bool:
    end = time.monotonic() + seconds
    while not cond() and time.monotonic() < end:
        time.sleep(0.01)
    return cond()


class Attachment:
    def __init__(self):
        self.detached, self.host_pid = False, 4242

    def alive(self):
        return not self.detached

    def detach(self):
        self.detached = True


class StopEvent:
    def __init__(self):
        self.asked = threading.Event()
        self.closed = False

    def is_set(self):
        return self.asked.is_set()

    def close(self):
        self.closed = True


def test_the_service_ends_in_good_order_on_its_stop_event(settings, monkeypatch):
    held = Attachment()
    monkeypatch.setattr(lib, "attach_fetcher", lambda db_path, log=print: held)
    event = StopEvent()
    monkeypatch.setattr(service, "stop_event", lambda: event)
    monkeypatch.setattr(service, "STOP_LOOK_S", 0.01)
    monkeypatch.setattr(service, "CHECK_SECONDS", 0.01)
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "8791")
    served: list = []

    def page(settings, port, *, link, stop=None, frame=None, **kw):
        link.touch()  # a page in touch: the fetcher held
        served.append(frame)
        event.asked.set()  # liminal-signal sets the integrator's stop event
        stop.wait()
        served.append("down")

    monkeypatch.setattr(lib, "page", lambda: page)
    lines: list[str] = []
    done: list[int] = []
    t = threading.Thread(target=lambda: done.append(service.run(settings, lines.append)), daemon=True)
    t.start()
    t.join(5)
    assert done == [0]  # ended by its event alone, nothing else set its stop
    assert served[-1] == "down" and held.detached  # the page down; the fetcher let go with a word
    assert served[0].stopping  # the page's frame stopped
    assert event.closed and any("asked to stop (its stop event)" in m for m in lines)
    assert lines[-1].startswith("service: ended")
