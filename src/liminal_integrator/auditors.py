"""The integrator's auditors (1.13.0): what runs them, and what their page asks.

The user, 2026-11-15: "auditors should run if a symbol is updated, or periodically"; "For the integrator, there needs
to be a plugin called auditor and it will manage the configuration of auditing data"; and 2026-11-18: "an auditor
plugin, for auditing sources and maintaining the integrity of the feeds; for the integrator".

The auditors are the library's (liminal_libs.auditing): the copy audit of the fetch cache, and the sweep of every
watched series. A pull is audited as it closes, by the feed's run that made it. What is left runs in a process of its
own (`liminal-integrator audit run`: `run` here): the sweep, what still waits in the cache, and an audit asked for.
The fetcher starts that process when the sweep is due (the policy's interval) or an audit was asked for; it ends when
its work is done or its time is spent, so nothing stays running. One at a time on a database (the claim `audit`),
whichever installation starts it; a copy that reads only audits nothing.

The page (the charts app's Plugins view, the auditor's entry) reads `overview` and asks `ask`: GET /api/auditor and
POST /api/auditor/run, the integrator's own routes (app.py). An audit asked for is a request on the fetcher's stack
(kind `audit`), so it is seen there like any other ask."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path

from . import lib

CLAIM = "audit"  # the auditors' process: one on a database
WHAT = ("audit", "sweep")  # what the page may ask: what waits in the cache (and a symbol), or a sweep now
PLUGIN = "auditor"


def db_of(app) -> Path:
    """The main file of the database an app's auditors work on."""
    db = getattr(app, "db_path", None)
    return Path(db) if db is not None else lib.layout.data_dir() / lib.layout.MAIN


def policy_of(app):
    """The auditors' policy as this app's login has it now (its plugin's options, read through the login: a choice
    made on the page a moment ago counts), and what is wrong with it in words ("" when nothing is). Without the
    plugin: the defaults."""
    plugin = lib.auditors().get(PLUGIN) or next(iter(lib.auditors().values()), None)
    if plugin is None:
        return lib.auditing.Policy(), ""
    try:
        login = plugin.login or app.login
        return plugin.settings(login.variables(list(plugin.options))), ""
    except lib.config.ConfigError as e:
        return lib.auditing.Policy(), str(e)


def sweep_due(store, policy, now: datetime | None = None) -> bool:
    """Whether the sweep is due: the policy has an interval, and the last run began that long ago (or none ran)."""
    if policy.sweep_hours is None:
        return False
    try:
        last = json.loads(store.kv_get(lib.auditing.LAST_KEY) or "null")
        began = datetime.fromisoformat(last["at"]) if last else None
    except (ValueError, KeyError, TypeError):
        began = None
    now = now or datetime.now(timezone.utc)
    return began is None or now - began >= timedelta(hours=policy.sweep_hours)


def overview(app) -> dict:
    """The auditors for their page: the policy, the cache by state and size, the last sweep, the findings; whether a
    plugin holds the options; the audits asked for and whether the auditors are at work now."""
    db = db_of(app)
    policy, problem = policy_of(app)
    plugin = lib.auditors().get(PLUGIN) or next(iter(lib.auditors().values()), None)
    with lib.Store(db) as store:
        out = lib.auditing.overview(store, policy)
        out["asked"] = [{"id": r["id"], "symbol": r["symbol"], "state": r["state"], "by": r["by"], "at": r["asked_at"],
                         "detail": r["detail"]} for r in store.requests_open() if r["kinds"] == (lib.AUDIT,)]
        out["sweep"]["due"] = sweep_due(store, policy)
    out["plugin"] = None if plugin is None else {"name": plugin.name, "title": plugin.title, "version": plugin.version,
                                                 "origin": plugin.origin}
    out["problem"] = problem
    out["running"] = any(h.key == CLAIM for h in lib.claims.held(db, CLAIM))  # whichever installation's
    return out


def ask(app, body: dict) -> dict:
    """The page's Audit now and Sweep now: a request of kind `audit` on the fetcher's stack, which the fetcher hands
    to the auditors' process at its next tick. `what`: audit (what waits in the cache; with `symbol`, that symbol's
    series gone over now, out of turn) or sweep (a sweep run now, from where the last one stopped). A copy that
    reads only asks nothing: its auditors audit nothing, and a request is a write."""
    if lib.read_only():
        raise lib.Refused(HTTPStatus.CONFLICT, "this copy reads only (LIMINAL_READONLY): nothing is asked of the "
                                               "auditors from here")
    what = str(body.get("what") or "")
    if what not in WHAT:
        raise lib.Refused(HTTPStatus.BAD_REQUEST, f"the auditors are asked one of: {', '.join(WHAT)}")
    symbol = str(body.get("symbol") or "").strip().upper()
    if symbol.startswith("*") or len(symbol) > 32:
        raise lib.Refused(HTTPStatus.BAD_REQUEST, f"not a symbol: {symbol[:40]!r}")
    asked = lib.EVERYTHING if what == "sweep" else symbol or lib.WAITING
    with lib.Store(db_of(app)) as store:
        r = store.request_put(asked, kinds=(lib.AUDIT,), by="page")
    said = ("a sweep now, from where the last one stopped" if what == "sweep" else
            f"{symbol}'s series gone over now" if symbol else "what waits in the fetch cache audited now")
    app.log(f"auditors: asked from the page: {said} (request #{r['id']})")
    return {"ok": True, "request": r["id"], "said": f"Asked: {said}.",
            "lines": ["The fetcher hands it to the auditors within a few seconds; what they find shows here."]}


def run(settings, log=print, sweep: bool = False, symbols=(), stop=None) -> dict:
    """The auditors' process's work, once: the audits asked for (the fetcher's stack), these `symbols` too, a sweep
    when one is due or asked (`sweep`), else what waits in the cache. Returns what was done, in numbers. A copy that
    reads only, and a database another auditors' process is on, are left alone and said. `stop` (1.14.0): asked
    before each series (Sweep.run's); stopped, the sweep's cursor keeps its place and an audit asked for is left
    open, handed to the auditors again by the next fetcher."""
    db = Path(settings.db_path)
    if settings.read_only:
        log("auditors: this copy reads only (LIMINAL_READONLY): nothing is audited from here")
        return {"note": "reads only"}
    policy = lib.auditing.policy_of(settings)
    lib.auditing.set_policy(policy)
    try:
        with lib.claims.exclusive(db, CLAIM, what="the auditors", log=log):
            return _work(settings, db, policy, log, sweep, symbols, stop)
    except lib.claims.Taken as e:
        log(f"auditors: at work on this database already ({e})")
        return {"note": "at work already"}


def _work(settings, db: Path, policy, log, sweep: bool, symbols, stop=None) -> dict:
    out: dict = {}
    with lib.Store(db) as store:
        asks = [r for r in store.requests_open() if r["kinds"] == (lib.AUDIT,)]
        only: set[tuple[str, str]] = set()
        unknown: list[str] = []
        for symbol in [*(r["symbol"] for r in asks), *(str(s).strip().upper() for s in symbols)]:
            if symbol == lib.EVERYTHING:
                sweep = True
            elif symbol and symbol != lib.WAITING:
                watched = {(w["source"], w["ticker"]) for w in store.watchlist(ticker=symbol)}
                only |= watched
                if not watched:
                    unknown.append(symbol)
        sweeper = lib.auditing.Sweep(store, feeds=lib.feed_profiles(settings), policy_=policy, log=log)
        if only:
            out["symbols"] = sweeper.run(only=only, stop=stop)
        if (sweep or sweep_due(store, policy)) and not (stop is not None and stop()):
            out["sweep"] = sweeper.run(stop=stop)
        elif not only:  # neither a sweep nor a symbol: what waits in the cache, and the cache kept in order
            closed = lib.auditing.recover(store, None, log)
            audited = lib.auditing.audit_pulls(store, policy_=policy, log=log, budget_s=policy.sweep_minutes * 60.0)
            kept = lib.auditing.tidy(store, policy)
            out["cache"] = {"recovered": closed, "pulls": len(audited),
                            "mismatch": sum(1 for a in audited if a.result == "mismatch"), **kept}
        words = said(out) + (f"; not watched by any feed: {', '.join(unknown)}" if unknown else "")
        if stop is not None and stop():
            out["stopped"] = True
            words += "; asked to stop: the rest at the next run"
        else:
            for r in asks:
                store.request_update(r["id"], state="done", detail=words)
    log(f"auditors: {words}")
    return out


def said(out: dict) -> str:
    """A run in a line."""
    parts = []
    for name, label in (("symbols", "asked"), ("sweep", "sweep")):
        got = out.get(name)
        if got:
            parts.append(f"{label}: {got['series']:,} series, {got['days']:,} days looked at, {got['pulls']:,} pulls audited, "
                         f"{got['holes']:,} holes found, {got['absent']:,} absent, {got['closed']:,} settled"
                         + (" (the round goes on next run)" if name == "sweep" and not got["complete"] else ""))
    cache = out.get("cache")
    if cache:
        parts.append(f"cache: {cache['pulls']:,} pulls audited ({cache['mismatch']:,} with a finding), "
                     f"{cache['recovered']:,} left open by a run that is gone closed, {cache['removed']:,} files removed")
    return "; ".join(parts) or "nothing to do"


def command(args, settings) -> int:
    """`liminal-integrator audit run|sweep|status [SYMBOL...]`: `run` is what the fetcher starts (the audits asked
    for, a sweep when due, else what waits in the cache); `sweep` runs one now; `status` says where the auditors
    stand; symbols after `run` are gone over now, out of turn."""
    log = lib.log_to(settings.db_path)
    if args.action == "status":
        from .app import IntegratorApp

        got = overview(IntegratorApp(log=log, db_path=settings.db_path))
        p, last, cache = got["policy"], got["sweep"]["last"], got["cache"]
        print(f"auditors: {'the plugin ' + got['plugin']['name'] + ' ' + got['plugin']['version'] if got['plugin'] else 'no plugin: the defaults'}"
              + (f"; {got['problem']}" if got["problem"] else "") + ("; at work now" if got["running"] else ""))
        print(f"  policy: audit on update {'on' if p['onUpdate'] else 'off'}, sweep every "
              f"{str(p['sweepHours']) + ' h' if p['sweepHours'] else 'never'} for {p['sweepMinutes']} min, on a mismatch "
              f"{'repair' if p['repair'] else 'flag'}, keep {p['keepDays']} days, cap {p['capGb']} GB, {p['repulls']} re-pulls")
        print(f"  cache: {cache['unverifiedBytes']:,} bytes not audited yet, {cache['keptBytes']:,} kept in all "
              f"({cache['folder']}){'' if cache['on'] else '; switched off (LIMINAL_FETCH_CACHE)'}")
        print(f"  sweep: last {last['at'] if last else 'never'}" + (f", {last['series']:,} series" if last else "")
              + f"; round {got['sweep']['round']}, at {got['sweep']['cursor'] or 'the start'}"
              + ("; due" if got["sweep"]["due"] else ""))
        counts = got["findings"]["counts"]
        print("  findings: " + (", ".join(f"{n:,} {state}" for state, n in sorted(counts.items())) or "none"))
        for f in got["findings"]["latest"][:args.limit]:
            print(f"    #{f['id']:<5} {f['state']:<8} {f['kind']:<12} {f['feed']}:{f['ticker'] or '*':<10} "
                  f"{f['timespan'] or '':<6} {f['count']:,}")
        return 0
    from .fetcher import listen_for_stop

    stop = listen_for_stop()  # its starter's TERM (1.14.0): its stop event on Windows, SIGTERM elsewhere
    out = run(settings, log, sweep=args.action == "sweep", symbols=args.symbols, stop=stop.is_set)
    print(said(out) if "note" not in out else out["note"])
    return 0
