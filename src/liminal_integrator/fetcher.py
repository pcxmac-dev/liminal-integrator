"""The fetcher: the program that collects the data and serves it; the chart app is its client.

The user, 2026-11-01: "the fetcher takes a symbol and uses the plugins 'to best effect (efficiency)
price / performance' retrieve all info about the symbol"; "the fetcher uses the plugins that it
knows about to assess the work, and then begin collecting data"; "the fetcher can take a
queue/stack of requests"; "the concept is to be able to use the app, which connects to the fetcher
for database access"; "so the app needs to funnel requests through the fetcher to the databases";
"i can look at the fetcher to see what the data looks like, i can use the 'app' to see what i want
to do".

The fetcher runs as the resident host `fetcher` (liminal_libs.host): one per database, up while
someone holds it (the integrator's page server while a page is in touch, `liminal-integrator serve`
or the app's `sync` by hand, a service that holds it for good: service.py) and gone once nobody
does. It owns the databases' writes, over its pipe alone: the page and the data API are served by
the integrator's own process (service.py, lib.page(): the monitoring views, the plugins, the
exchanges, the news, the globe) at LIMINAL_FETCHER_PORT, and the chart app is a front that funnels
every request of its pages there (the user, 2026-11-03: "for the webserver / ports, i just
integrator, and charts": two listeners on the machine).

Its work (Fetcher.run), between ticks of TICK_SECONDS while it is up:
- the requests (liminal_libs.storage.requests): the newest ask first, then its standing work in
  order. For each it assesses the work over the plugins set up here (`assess`: what each can give
  for the symbol, by cost and capability, from the delivery scheme in liminal_libs.sourcing), asks
  every feed of the plan for the symbol before anything else (collector.request_priority) and holds
  those feeds' runs (the hosts feed-NAME) until each has served it or its run has ended;
- the standing pass: every PASS_HOURS while it is up, once new data can exist (`next_due`: the
  feeds' calendars and their plans' publication delays) or a run stopped short (its caps): every
  feed's run held, the closed months' copy (the host history), the extras (the publishers' due
  feeds, the stores' pass, the composites and derived frames: the app's `sync --extras-only`) in a
  process of their own, and the plugins that fetch on their own through their queue (runner);
- its status in the main file (storage.requests.STATUS_KEY), for every page, and over its pipe
  (`handle`).

The plugins it loads are every plugin found, or the ones it is told (`--plugins twse,tiingo`, or
`none`: liminal_libs.sources.registry's selection, LIMINAL_PLUGINS_LOADED, inherited by every process
it starts); its status says which were loaded and which left out. An integrator of its own
(`--name`, LIMINAL_INTEGRATOR_NAME: the user, 2026-11-03, "multiple integrators can address
databases") runs on its own database (store/data/<name>/liminal.db unless `--db`) with its own page
port and plugins, beside the one and only; the host `fetcher` is one per database, so each database
has one fetcher, and the machine's ledgers (a key's uses) are shared by key, whichever spends them.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import lib

HOST = lib.FETCHER
KINDS = lib.KINDS  # what a request can ask about a symbol today (the contract's verbs bring the rest)
TICK_SECONDS = 2.0  # the loop looks at its requests and runs this often
PASS_HOURS = 1.0  # the standing pass, at most this often (LIMINAL_SYNC_HOURS)
PAGE_PORT = 8785  # its page and data API (LIMINAL_FETCHER_PORT; 0: a free one; none: no page)
NAME_VAR = "LIMINAL_INTEGRATOR_NAME"  # this integrator's name when it is not the only one (an instance of its own)
SERVE_TIMEOUT_S = 6 * 3600  # a request whose feeds have not served it by then has failed
STATUS_EVERY_S = 30.0  # the status written at least this often while something goes on
Log = Callable[[str], None]


def pass_hours() -> float:
    try:
        return float(lib.config.setting("LIMINAL_SYNC_HOURS") or PASS_HOURS)
    except ValueError:
        return PASS_HOURS


def page_port() -> int | None:
    """The port of the fetcher's page and data API (0: a free one; none, off: no page at all)."""
    raw = (lib.config.setting("LIMINAL_FETCHER_PORT") or "").strip().lower()
    if raw in ("none", "off"):
        return None
    try:
        return int(raw) if raw else PAGE_PORT
    except ValueError:
        return PAGE_PORT


def instance_name() -> str:
    """This integrator's name (LIMINAL_INTEGRATOR_NAME): "" for the one and only, else the name it was
    installed or served under (`--name`), on a database of its own."""
    return (lib.config.setting(NAME_VAR) or "").strip()


def check_name(name: str) -> str:
    """A name an integrator can be installed under: letters, digits, `-` and `_` (up to 40, the first
    a letter or digit): a task's or a unit's name, a folder's. ValueError otherwise."""
    if not name or len(name) > 40 or not name[0].isalnum() or not all(c.isalnum() or c in "-_" for c in name):
        raise ValueError(f"an integrator's name is letters, digits, - and _ (up to 40), not {name!r}")
    return name


def instance_db(name: str) -> Path:
    """The database an integrator named `name` runs on unless told another (`--db`): a folder of its
    own in the data folder (store/data/<name>/liminal.db), its feeds' files beside it."""
    return lib.layout.data_dir() / check_name(name) / lib.layout.MAIN


def plugins_state() -> dict:
    """The plugins this process loaded (lib.plugins_loaded) and the selection that applied
    (lib.selection: `--plugins`, LIMINAL_PLUGINS_LOADED): all, the names, or none."""
    chosen = lib.selection()
    return {"selection": chosen.text, "loaded": lib.plugins_loaded(), "leftOut": list(chosen.left_out),
            "unknown": list(chosen.unknown)}


def plugins_line(state: dict) -> str:
    """One line on the plugins loaded, for the log, the status and the page."""
    loaded = ", ".join(state.get("loaded") or []) or "none"
    asked = state.get("selection") or "all"
    return (f"plugins loaded: {loaded}" + (f" ({asked} asked for)" if asked != "all" else "")
            + (f"; left out: {', '.join(state['leftOut'])}" if state.get("leftOut") else "")
            + (f"; unknown: {', '.join(state['unknown'])}" if state.get("unknown") else ""))


def next_due(settings, profiles: dict, now: datetime, exchanges: dict[str, set[str]] | None = None) -> datetime | None:
    """The earliest moment any feed set up here can have new data (freshness.expected, per feed
    and asset class on its plan; a feed's stocks listed outside the US by their exchanges' days:
    `exchanges` is {feed: {MIC}}, Store.watch_exchanges): the standing pass waits for it. None:
    not known."""
    due = []
    for name, p in profiles.items():
        try:
            tier = settings.for_source(name).tier
        except Exception:  # noqa: BLE001 - a feed not set up here says nothing
            continue
        for asset in sorted(p.assets):
            abroad = sorted((exchanges or {}).get(name, ())) if asset == "stock" else []
            for exchange in (None, *abroad):
                e = lib.freshness.expected(lib.freshness.hours(name, asset), tier, now, exchange)
                if e.next_due is not None:
                    due.append(e.next_due)
    return min(due) if due else None


def _aware(t: datetime | None) -> datetime | None:
    return t.replace(tzinfo=timezone.utc) if t is not None and t.tzinfo is None else t


# -- assessing a symbol ------------------------------------------------------------------------
@dataclass
class Assessment:
    """What the plugins can do for one symbol, and the plan: each job (an era of one resolution in
    one market) to the plugin that delivers it by the scheme (sourcing: unique eras to the only
    plugin that has them, common ones to the plugin finishing soonest within its caps)."""
    symbol: str
    asset: str | None
    offers: list[dict] = field(default_factory=list)  # what each plugin can give: resolution, since, latency, cost
    jobs: list[dict] = field(default_factory=list)  # the plan, in the user's order: days, minutes, seconds
    feeds: list[str] = field(default_factory=list)  # the plugins of the plan, in order
    live: list[list[str]] = field(default_factory=list)  # [(plugin, what)] for the current session, freshest first
    note: str = ""  # why nothing can be done, when nothing can
    retired: str | None = None  # no longer listed since this day: its history completed, no new data asked for

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "asset": self.asset, "offers": self.offers, "jobs": self.jobs,
                "feeds": self.feeds, "live": self.live, "note": self.note, "retired": self.retired}


class Assessor:
    """What the plugins set up here can do for a symbol, and when any of them can have new data: the
    feed profiles (lib.feed_profiles) read once for a moment, with the store and the settings; one
    per tick of the fetcher (take_requests, standing_pass), one per command."""

    def __init__(self, store, settings, now: datetime | None = None):
        self.store, self.settings = store, settings
        self.now = now or datetime.now(timezone.utc)
        self.profiles = {n: p for n, p in lib.feed_profiles(settings).items() if p.assets}

    def assess(self, symbol: str, kinds=("bars",)) -> Assessment:
        """Assess the work for `symbol` (as typed: SPCX::NASDAQ, EUR/USD, TSE:7203; the assessment is
        under the stored ticker, SPCX, EURUSD, 7203.T) over the plugins set up here. A symbol nobody
        watches yet goes on the watchlist of every feed that can collect it first; then each feed's
        offers for its asset class (the standing scheme's), and the plan's jobs to the feeds holding it."""
        store, now, profiles = self.store, self.now, self.profiles
        spec = lib.resolve(symbol)
        symbol = spec.ticker
        today = now.astimezone(lib.ET).date()
        rows = store.watchlist(ticker=symbol)
        if not rows:
            for name, p in profiles.items():
                if spec.asset in p.assets and lib.supports(name, spec):
                    store.watch_spec(name, spec)
            rows = store.watchlist(ticker=symbol)
        if not rows:
            abroad = spec.asset == "stock" and lib.is_foreign(spec.exchange)
            return Assessment(symbol, None, note=f"no feed set up here carries {spec.exchange} listings" if abroad
                              else "no feed set up here collects it")
        asset = rows[0]["asset"]
        # A retired symbol (no longer listed) is held too: the user, 2026-11-02: "if however, the retired
        # stock data is still available on any of the sources, complete the retired symbol". Its feeds'
        # runs fill what history they still have and ask for nothing after its last listed day
        # (collector.retired_end); the app asks for it only while some feed's history is incomplete.
        retired = max((str(r["retired_on"]) for r in rows if r.get("retired_on")), default=None) \
            if all(r.get("retired_on") for r in rows) else None
        holding = [r["source"] for r in rows
                   if r["source"] in profiles and asset in profiles[r["source"]].assets and r.get("closed_at") is None]
        scheme = lib.sourcing.Scheme.standing(store, profiles, now)
        offers = []
        for o in scheme.offers:
            if o.asset != asset or o.source not in holding:
                continue
            years = max((today - o.since).days, 0) / 365.25
            offers.append({"plugin": o.source, "resolution": o.resolution, "market": o.market, "since": o.since.isoformat(),
                           "latency": o.latency, "requests": round(o.requests(years), 1), "capacity": round(o.capacity, 1)})
        jobs = []
        for e in scheme.eras:
            if e.asset != asset:
                continue
            first = next((s for s in e.sources if s in holding), None)
            if first is None:
                continue
            jobs.append({"plugin": first, "resolution": e.resolution, "market": e.market, "start": e.start.isoformat(),
                         "end": e.end.isoformat() if e.end else None, "unique": e.unique,
                         "days": round(e.days.get(first, 0.0), 3)})
        if spec.asset == "stock" and lib.is_foreign(spec.exchange):
            # a listing abroad: the eras are the US market's cuts between feeds that do not carry it, so
            # each holding feed's work is one job per resolution, from its earliest era on (600519.SS on
            # Tiingo showed three day eras cut at Massive's and Alpaca's starts: 2026-11-03)
            merged: dict[tuple, dict] = {}
            for j in jobs:
                key = (j["plugin"], j["resolution"], j["market"])
                was = merged.get(key)
                if was is None:
                    merged[key] = {**j, "unique": True}
                else:
                    was["start"] = min(was["start"], j["start"])
                    was["end"] = None if was["end"] is None or j["end"] is None else max(was["end"], j["end"])
                    was["days"] = round(was["days"] + j["days"], 3)
            jobs = list(merged.values())
        order = {r: i for i, r in enumerate(lib.sourcing.JOBS)}
        jobs.sort(key=lambda j: (order.get(j["resolution"], len(order)), j["start"]))
        feeds = list(dict.fromkeys(j["plugin"] for j in jobs))
        live = [[s, w] for s, w in scheme.live.get(asset, []) if s in holding and not retired] if "live" in kinds else []
        note = "" if feeds else ("no plugin set up here delivers its history" if holding
                                 else "its feeds are closed, or not set up here")
        return Assessment(symbol, asset, offers, jobs, feeds, live, note, retired)

    def next_due(self, exchanges: dict[str, set[str]] | None = None) -> datetime | None:
        """The earliest moment any feed set up here can have new data (next_due)."""
        return next_due(self.settings, self.profiles, self.now, exchanges)


def assess(store, settings, symbol: str, kinds=("bars",), now: datetime | None = None) -> Assessment:
    """A symbol assessed once (Assessor.assess): the feed profiles read for it alone."""
    return Assessor(store, settings, now).assess(symbol, kinds)


# -- the fetcher ---------------------------------------------------------------------------------
class Fetcher:
    """The fetcher's work and state (one per process: the host `fetcher`)."""

    def __init__(self, settings, log: Log = print, db_path: Path | None = None, login=None):
        from .app import IntegratorApp  # app.py imports lib; nothing of the fetcher

        self.settings = settings
        self.db_path = Path(db_path or settings.db_path)
        self.log = log
        # The integrator as an app of the frame (app.py): its plugins, attached at the host's start
        # (run_host) with its login, the one way to their keys (the user environment until a daemon
        # holds a login session of its own).
        self.app = IntegratorApp(log=log, login=login)
        self.login = self.app.login
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.lock = threading.RLock()
        self.feeds: dict[str, object] = {}  # feed -> its run's attachment (liminal_libs.host), held
        self.by_pass: set[str] = set()  # the feeds the standing pass holds (until their runs end)
        self.history = None  # the closed months' copy, held
        self.extras = None  # the extras' process
        self.workers: threading.Thread | None = None  # the plugins that fetch on their own
        self.active: dict[int, dict] = {}  # request id -> its symbol, feeds, when asked, its detail
        self.last_pass: float | None = None
        self.last_pass_at: datetime | None = None
        self.next_due: datetime | None = None
        self.pass_asked = False
        self.page_url: str | None = None
        self.host = None  # the Host serving this fetcher (its clients, for the status)
        self.ticks = 0
        self._status_at = 0.0
        self._status_last: str | None = None

    # -- what clients ask (the host's handle, and the fetcher's own page) -------------------------
    def wake_up(self) -> None:
        self.wake.set()

    def ask_pass(self) -> None:
        """A standing pass now (resuming fetching, `sync` by hand, the page)."""
        with self.lock:
            self.pass_asked = True
        self.wake.set()

    def handle(self, msg: dict) -> dict:
        if msg.get("status"):
            return self.status()
        if msg.get("pass"):
            self.ask_pass()
            return {"ok": True}
        if msg.get("wake"):
            self.wake_up()
            return {"ok": True}
        return {"error": "nothing to ask the fetcher: status, pass or wake"}

    def status(self) -> dict:
        with self.lock:
            feeds = {n: a for n, a in self.feeds.items() if a is not None}
            return {
                "pid": os.getpid(), "page": self.page_url, "name": instance_name(), "plugins": plugins_state(),
                "busy": bool(self.active or feeds or self.pass_asked or (self.history is not None and self._alive(self.history))),
                "active": [{"id": i, "symbol": a["symbol"], "feeds": a["feeds"], "detail": a.get("detail")}
                           for i, a in self.active.items()],
                "feeds": sorted(feeds), "passFeeds": sorted(self.by_pass),
                "history": self.history is not None and self._alive(self.history),
                "lastPass": self.last_pass_at.isoformat(timespec="seconds") if self.last_pass_at else None,
                "nextDue": self.next_due.isoformat(timespec="seconds") if self.next_due else None,
                "passHours": pass_hours(), "clients": self.host.clients() if self.host is not None else [],
                "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }

    # -- the loop ------------------------------------------------------------------------------
    def run(self, stop: threading.Event | None = None) -> None:
        """The fetcher's work until `stop` (the host's: its clients gone). Its own store, opened
        here and closed at the end; the feeds' runs let go at the end (each stops at its next
        request)."""
        if stop is not None:
            self.stop = stop
        store = lib.Store(self.db_path, check_same_thread=False)
        try:
            name = instance_name()
            self.log(f"fetcher{' ' + name if name else ''}: {plugins_line(plugins_state())}")
            n = store.request_reset()
            if n:
                self.log(f"fetcher: {n} request(s) left by the fetcher before: waiting again")
            while not self.stop.is_set():
                now = datetime.now(timezone.utc)
                try:
                    self.tick(store, now)
                except Exception as e:  # noqa: BLE001 - a tick's failure is logged; the next comes
                    self.log(f"fetcher: {type(e).__name__}: {e}")
                self.wake.wait(TICK_SECONDS)
                self.wake.clear()
        finally:
            self.let_go()
            try:
                self.write_status(store, datetime.now(timezone.utc), force=True)
            except Exception:  # noqa: BLE001 - the status is a courtesy at the end
                pass
            store.close()

    def tick(self, store, now: datetime) -> None:
        self.ticks += 1
        self.take_requests(store, now)
        self.check_active(store, now)
        if self.pass_due(store, now):
            self.standing_pass(store, now)
        self.settle_feeds()
        self.write_status(store, now)

    # -- requests ------------------------------------------------------------------------------
    def take_requests(self, store, now: datetime) -> None:
        """Every waiting request taken: assessed, its feeds asked for the symbol first and their
        runs held. Halted: they wait (a pause leaves the asks their fetches)."""
        paused = lib.collector.pause_state(store, now)
        if paused and paused.get("halt"):
            return
        s = self.settings
        assessor = None  # the profiles read once for the tick, when a request comes
        while (r := store.request_next(now)) is not None:
            if s.offline or s.read_only:
                # offline: assessed all the same (no request: the plugins' records and the watchlist), so
                # the page shows which feeds would be asked (the user, 2026-11-03: going through the UI
                # plugin by plugin on an offline copy); reads only: nothing written beyond the request
                plan = None
                if not s.read_only:
                    try:
                        assessor = assessor or Assessor(store, s, now)
                        plan = assessor.assess(r["symbol"], r["kinds"]).as_dict()
                    except Exception:  # noqa: BLE001 - the plan is a courtesy here
                        plan = None
                asked = f"; it would ask {', '.join(plan['feeds'])}" if plan and plan.get("feeds") else \
                    f"; {plan['note']}" if plan and plan.get("note") else ""
                store.request_update(r["id"], state="failed", plan=plan, now=now,
                                     detail="nothing fetched: this fetcher is offline or reads only (LIMINAL_OFFLINE, "
                                            "LIMINAL_READONLY)" + asked)
                continue
            try:
                assessor = assessor or Assessor(store, s, now)
                a = assessor.assess(r["symbol"], r["kinds"])
            except Exception as e:  # noqa: BLE001 - this request fails; the next goes on
                store.request_update(r["id"], state="failed", detail=f"could not be assessed: {type(e).__name__}: {e}", now=now)
                self.log(f"fetcher: {r['symbol']}: could not be assessed: {type(e).__name__}: {e}")
                continue
            if not a.feeds:
                store.request_update(r["id"], state="failed", plan=a.as_dict(), detail=a.note or "nothing to collect", now=now)
                self.log(f"fetcher: {r['symbol']}: {a.note or 'nothing to collect'}")
                continue
            lib.collector.request_priority(store, a.symbol, now)
            held = [name for name in a.feeds if self.hold_feed(name)]
            detail = f"on {', '.join(held)}" if held else "no feed's run could be started"
            if a.retired:
                detail += f" (retired since {a.retired}: its history completed, no new data asked for)"
            store.request_update(r["id"], state="collecting", plan=a.as_dict(), detail=detail, now=now)
            with self.lock:
                self.active[r["id"]] = {"symbol": a.symbol, "feeds": a.feeds, "asked": now, "asked_iso": r["asked_at"],
                                        "since": time.monotonic(), "detail": detail}
            self.log(f"fetcher: {a.symbol} ({r['by']}): {', '.join(a.feeds)} asked for it first"
                     + (f"; live from {a.live[0][0]}" if a.live else ""))

    def check_active(self, store, now: datetime) -> None:
        """Each request being collected: done once every feed of its plan has served the symbol
        (synced since it was asked), or its run has ended; failed when none served it."""
        for rid, a in list(self.active.items()):
            r = store.request_get(rid)
            if r is None or r["state"] != "collecting":  # cancelled, or gone
                with self.lock:
                    self.active.pop(rid, None)
                continue
            if r["asked_at"] != a["asked_iso"]:  # asked anew: the feeds are asked again, from now
                a["asked"], a["asked_iso"] = now, r["asked_at"]
                lib.collector.request_priority(store, a["symbol"], now)
                for name in a["feeds"]:
                    self.hold_feed(name)
            served, ended, pending = [], [], []
            for name in a["feeds"]:
                row = next(iter(store.watchlist(name, a["symbol"])), None)
                synced = _aware(row["synced_at"]) if row is not None else None
                if synced is not None and synced >= a["asked"]:
                    served.append(name)
                elif name not in self.feeds or not self._alive(self.feeds[name]):
                    ended.append(name)
                else:
                    pending.append(name)
            if pending and time.monotonic() - a["since"] < SERVE_TIMEOUT_S:
                detail = (f"served by {', '.join(served)}; " if served else "") + f"waiting for {', '.join(pending)}"
                if detail != a.get("detail"):
                    a["detail"] = detail
                    store.request_update(rid, detail=detail)
                continue
            state = "done" if served else "failed"
            detail = (f"served by {', '.join(served)}" if served else "served by no feed") \
                + (f"; {', '.join(ended)}: its run ended without it" if ended else "") \
                + (f"; {', '.join(pending)}: not served within {SERVE_TIMEOUT_S // 3600:g} h" if pending else "")
            store.request_update(rid, state=state, detail=detail, now=now)
            with self.lock:
                self.active.pop(rid, None)
            self.log(f"fetcher: {a['symbol']}: {detail}")

    # -- the feeds' runs -----------------------------------------------------------------------
    @staticmethod
    def _alive(attachment) -> bool:
        try:
            return bool(attachment is not None and attachment.alive())
        except Exception:  # noqa: BLE001 - a broken pipe is a run gone
            return False

    def hold_feed(self, name: str) -> bool:
        """Hold feed `name`'s run (the host feed-NAME, started if none answers). Whether it is held."""
        with self.lock:
            held = self.feeds.get(name)
        if self._alive(held):
            return True
        att = lib.feed_run(name, self.db_path, log=self.log)
        with self.lock:
            if att is None:
                self.feeds.pop(name, None)
                return False
            self.feeds[name] = att
        return True

    def settle_feeds(self) -> None:
        """Runs that ended are forgotten; a run held for nobody (no request needs it, the standing
        pass does not hold it) is let go: it stops at its next request."""
        with self.lock:
            needed = {name for a in self.active.values() for name in a["feeds"]}
            for name, att in list(self.feeds.items()):
                if not self._alive(att):
                    self.feeds.pop(name)
                    self.by_pass.discard(name)
                elif name not in needed and name not in self.by_pass:
                    att.detach()
                    self.feeds.pop(name)
            if self.history is not None and not self._alive(self.history):
                self.history = None

    def let_go(self) -> None:
        """Every run let go (each stops at its next request), the extras left to finish."""
        with self.lock:
            for att in list(self.feeds.values()) + [self.history]:
                if att is not None:
                    try:
                        att.detach()
                    except Exception:  # noqa: BLE001 - a run gone already
                        pass
            self.feeds, self.by_pass, self.history = {}, set(), None

    # -- the standing pass ---------------------------------------------------------------------
    def pass_due(self, store, now: datetime) -> bool:
        """Whether a standing pass is due: asked for, or never run; else PASS_HOURS after the last
        and new data possible since (next_due), or a run stopped short (its caps: more to do)."""
        s = self.settings
        if s.offline or s.read_only:
            return False
        with self.lock:
            if self.pass_asked:
                return True
            if self.last_pass is None:
                return True
            if time.monotonic() - self.last_pass < pass_hours() * 3600:
                return False
            if self.next_due is None or now >= self.next_due:
                return True
        return any(r.get("status") == "stopped" for r in store.last_runs().values())

    def standing_pass(self, store, now: datetime) -> dict:
        """One pass: every feed set up here held (its run started if none goes; a closed archive and
        a feed fetching elsewhere left alone), the closed months' copy, the extras in a process of
        their own, the plugins that fetch on their own. Not while fetching is paused or halted."""
        s = self.settings
        with self.lock:
            self.pass_asked = False
            self.last_pass, self.last_pass_at = time.monotonic(), now
        paused = lib.collector.pause_state(store, now)
        if paused:
            self.log("fetcher: fetching is " + ("halted" if paused.get("halt") else "paused") + ": no pass")
            return {"started": [], "why": "halted" if paused.get("halt") else "paused"}
        busy = lib.proc.run_holders(self.db_path)
        if None in busy:
            self.log("fetcher: the whole database is locked (its data is being moved): no pass")
            return {"started": [], "why": "the whole database is locked"}
        assessor = Assessor(store, s, now)
        profiles = assessor.profiles  # the feeds set up here
        started, going, unset = [], [], []
        for name in lib.providers():
            if not (profiles.get(name) and profiles[name].assets):
                unset.append(name)  # not set up here (its key): nothing it could fetch
                continue
            if lib.feed_closed(s, name):
                continue  # a closed archive: every symbol's archive is complete
            if name in busy and name not in self.feeds:
                going.append(name)
                continue
            if self.hold_feed(name):
                with self.lock:
                    self.by_pass.add(name)
                started.append(name)
        if lib.history_due(s) and not self._alive(self.history):
            self.history = lib.history_run(self.db_path, log=self.log)
        if self.extras is None or self.extras.poll() is not None:
            exe = Path(sys.executable)
            quiet = exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe
            self.extras = self._spawn([str(quiet), "-m", lib.host.APP_MODULE, "sync", "--extras-only"])
        if lib.plugin_fetchers() and (self.workers is None or not self.workers.is_alive()):
            self.workers = threading.Thread(target=self._run_plugins, name="fetcher-plugins", daemon=True)
            self.workers.start()
        with self.lock:
            self.next_due = assessor.next_due(store.watch_exchanges())
        self.log(f"fetcher: pass: {', '.join(started) or 'no feed'} held"
                 + (f"; fetching already: {', '.join(going)}" if going else "")
                 + (f"; not set up here: {', '.join(unset)}" if unset else "")
                 + "; the extras in a process of their own"
                 + (f"; nothing new before {self.next_due.astimezone(lib.ET):%a %H:%M} ET" if self.next_due else ""))
        return {"started": started, "going": going, "unset": unset}

    def _run_plugins(self) -> None:
        try:
            out = lib.runner.Runner(lambda: lib.Store(self.db_path, check_same_thread=False), self.settings, self.log).run()
            for p, o in out.items():
                self.log(f"fetcher: {p}: " + ", ".join(f"{k} {v}" for k, v in o.items() if v))
        except Exception as e:  # noqa: BLE001 - the plugins' workers failing is theirs
            self.log(f"fetcher: the plugins' own fetching failed: {type(e).__name__}: {e}")

    def _spawn(self, args: list[str]):
        return subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                **lib.proc.no_window())

    # -- the status ----------------------------------------------------------------------------
    def write_status(self, store, now: datetime, force: bool = False) -> None:
        """The status into the main file (storage.requests.STATUS_KEY) when it changed, and at least
        every STATUS_EVERY_S while something goes on: every page reads it there."""
        st = self.status()
        text = json.dumps({k: v for k, v in st.items() if k != "at"}, sort_keys=True)
        due = force or text != self._status_last or (st["busy"] and time.monotonic() - self._status_at >= STATUS_EVERY_S)
        if not due:
            return
        self._status_last, self._status_at = text, time.monotonic()
        lib.write_status(store, st)


def page_url_of(port: int | None) -> str | None:
    """Where the integrator serves its page and the data API (service.py): None without a port."""
    return f"http://127.0.0.1:{port}/" if port else None


def run_host(settings, log: Log | None = None, port: int | None = None, rescan: bool | None = None) -> str:
    """The fetcher's process: the host `fetcher` of this database and the fetcher's work under it,
    over its pipe alone (no HTTP: the integrator's own process serves the page and the data API at
    `port`, LIMINAL_FETCHER_PORT by default, which the status names). `rescan` is the integrator's
    page server's now (kept for the callers). Returns why the host stopped (its clients gone)."""
    log = log or lib.log_to(settings.db_path)
    h = lib.Host(HOST, settings.db_path, log=log)
    f = Fetcher(settings, log)
    f.host = h
    attached = f.app.attach_plugins()  # the stock-data plugins, with the integrator's login
    log(f"fetcher: {len(attached)} plugins attached: {', '.join(attached) or 'none'}")
    f.page_url = page_url_of(page_port() if port is None else port)
    return h.serve(f.run, handle=f.handle)
