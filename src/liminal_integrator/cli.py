"""The integrator's command line: `liminal-integrator serve|status|request|pass|cancel|host` and
`liminal-integrator service install|remove|status|run`, `--daemon` on serve, install and run for
the fetcher held for good; `--plugins` for the plugins loaded (names, or none); `--name` (with
`--db`, `--port`) for an integrator of its own, on its own database. The app's own command line
answers the same (`liminal fetcher ...`, `liminal service ...`), through here."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from . import fetcher, lib, service


def cmd_fetcher(args, settings) -> int:
    """`serve` keeps the fetcher's page here at its port (LIMINAL_FETCHER_PORT, 8785), open in the
    browser, the fetcher running while a page is in touch, or with `--daemon` held for good so it
    collects what it can on its own (service.py), until Ctrl+C; `status` shows its stack and state;
    `request SYMBOL...` asks it for symbols; `pass` asks for a standing pass now; `cancel --id N`
    takes a request back; `host` runs a fetcher here, in the foreground, nothing holding it."""
    log = lib.log_to(settings.db_path)
    if args.action == "host":
        fetcher.run_host(settings, log, port=args.port)
        return 0
    if args.action == "serve":
        return service.run(settings, log, open_browser=not args.no_browser, port=args.port, daemon=args.daemon)
    if args.action == "status":
        with lib.Store(settings.db_path) as store:
            status = lib.read_status(store)
            rows = store.request_rows(limit=args.limit)
        if status is None:
            print("the fetcher has never run on this database")
        else:
            who = f"fetcher {status['name']}" if status.get("name") else "fetcher"
            print(f"{who}: pid {status.get('pid')}, {'busy' if status.get('busy') else 'idle'}, page {status.get('page') or 'none'}, "
                  f"clients {status.get('clients')}, last pass {status.get('lastPass') or 'never'}, "
                  f"next due {status.get('nextDue') or 'unknown'}, feeds held: {', '.join(status.get('feeds') or []) or 'none'}")
            if status.get("plugins"):
                print(f"  {fetcher.plugins_line(status['plugins'])}")
        for r in rows:
            print(f"  #{r['id']:<5} {r['symbol']:<12} {r['state']:<11} {r['by']:<8} {','.join(r['kinds']):<10} {r['asked_at'][:19]}  "
                  f"{r['detail'] or ''}")
        if not rows:
            print("  no requests")
        return 0
    if args.action == "request":
        if not args.symbols:
            print("request: which symbols?")
            return 2
        with lib.Store(settings.db_path) as store:
            rows = [store.request_put(stored_ticker(t), kinds=args.kinds.split(","), by="cli") for t in args.symbols]
        for r in rows:
            print(f"#{r['id']} {r['symbol']}: {r['state']} ({','.join(r['kinds'])})")
        held = lib.attach_fetcher(settings.db_path, log)
        if held is None:
            print("no fetcher answered: the requests wait on its stack for the next one")
            return 1
        try:
            held.ask(wake=True)
            if args.wait:
                lib.wait_for_requests(settings.db_path, [r["id"] for r in rows], held, log)
        finally:
            held.detach()
        return 0
    if args.action == "cancel":
        if args.id is None:
            print("cancel: which request (--id)?")
            return 2
        with lib.Store(settings.db_path) as store:
            ok = store.request_cancel(args.id)
        print(f"#{args.id}: {'cancelled' if ok else 'not open'}")
        return 0 if ok else 1
    held = lib.attach_fetcher(settings.db_path, log)  # pass
    if held is None:
        print("no fetcher answered (and none could be started): see logs/liminal.log")
        return 1
    try:
        print(json.dumps(held.ask(**{"pass": True})))
        lib.wait_for_fetcher(held, log)
    finally:
        held.detach()
    return 0


def cmd_service(args, settings) -> int:
    """The integrator's service from your logon (service.py): install, remove, status, or run (what
    the installed service runs: `serve` without the browser); `--daemon` holds the fetcher for good."""
    log = lib.log_to(settings.db_path)
    daemon = bool(getattr(args, "daemon", False))
    name = getattr(args, "name", None) or ""
    port = getattr(args, "port", None)
    if args.action == "run":
        return service.run(settings, log, daemon=daemon, port=port)
    if args.action == "install":
        return service.install(settings, log, daemon=daemon, name=name, port=port, plugins=getattr(args, "plugins", None),
                               db_path=Path(args.db).expanduser() if getattr(args, "db", None) else None)
    if args.action == "remove":
        return service.remove(settings, log, name=name)
    return service.status(settings, log, name=name)


def apply_instance(args) -> bool:
    """`--name`, `--db` and `--plugins` applied to this process before its settings load, and so to
    the ones it starts (its environment): the integrator's name (LIMINAL_INTEGRATOR_NAME) and its
    own database (LIMINAL_DB: `--db`, else store/data/<name>/liminal.db: fetcher.instance_db), the
    plugins loaded (LIMINAL_PLUGINS_LOADED: names, or none; lib.select). Whether anything was set.
    ValueError: a name that cannot be one."""
    name = getattr(args, "name", None)
    db = getattr(args, "db", None)
    plugins = getattr(args, "plugins", None)
    changed = False
    if name:
        os.environ[fetcher.NAME_VAR] = fetcher.check_name(name)
        changed = True
    if db:
        os.environ["LIMINAL_DB"] = str(Path(db).expanduser())
        changed = True
    elif name:
        os.environ["LIMINAL_DB"] = str(fetcher.instance_db(name))
    if plugins is not None:
        lib.select(plugins)
        changed = True
    return changed


def add_instance_arguments(p: argparse.ArgumentParser, actions: str) -> None:
    """`--name`, `--db`, `--plugins`: an integrator of its own, and the plugins it loads."""
    p.add_argument("--name", help=f"{actions}: this integrator's name when it is not the only one (LIMINAL_INTEGRATOR_NAME): "
                                  "on a database of its own (store/data/NAME/liminal.db unless --db) and a page port of its "
                                  "own (--port)")
    p.add_argument("--db", help=f"{actions}: the database, its main file (LIMINAL_DB)")
    p.add_argument("--plugins", help=f"{actions}: the plugins loaded, their names comma separated (a part's name keeps its "
                                     "plugin), or none for no plugin at all; every plugin found without it "
                                     "(LIMINAL_PLUGINS_LOADED)")


def add_fetcher_arguments(p: argparse.ArgumentParser) -> None:
    """The `fetcher` command's arguments (the app's parser adds the same)."""
    p.add_argument("action", nargs="?", default="serve", choices=["serve", "status", "request", "pass", "cancel", "host"])
    p.add_argument("symbols", nargs="*", help="request: the symbols")
    p.add_argument("--id", type=int, help="cancel: the request")
    p.add_argument("--kinds", default="bars", help="request: what about them, comma separated (bars, live)")
    p.add_argument("--wait", action="store_true", help="request: wait here until each request has ended")
    p.add_argument("--limit", type=int, default=40, help="status: requests shown")
    p.add_argument("--port", type=int, help="serve, host: the page's port (LIMINAL_FETCHER_PORT, 8785; 0: a free one)")
    p.add_argument("--no-browser", action="store_true", help="serve: do not open its page")
    p.add_argument("--daemon", action="store_true",
                   help="serve: hold the fetcher for good as well, so it collects what it can on its own; otherwise it "
                        "runs only while a page is in touch")
    add_instance_arguments(p, "serve, host")


def add_service_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("action", nargs="?", default="status", choices=["install", "remove", "status", "run"])
    p.add_argument("--daemon", action="store_true",
                   help="install, run: the fetcher held for good (it collects what it can on its own); otherwise it "
                        "runs only while a page is in touch")
    p.add_argument("--port", type=int, help="install, run: the page's port (LIMINAL_FETCHER_PORT, 8785; 0: a free one)")
    add_instance_arguments(p, "install, run (status, remove: --name)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="liminal-integrator", description=__doc__)
    sub = p.add_subparsers(dest="command")
    f = sub.add_parser("fetcher", help="the fetcher: serve (its page here, in the browser; --daemon holds the fetcher "
                                      "for good), status, request SYMBOL..., pass, cancel --id N, host")
    add_fetcher_arguments(f)
    f.set_defaults(func=cmd_fetcher)
    s = sub.add_parser("service", help="the integrator's service from your logon (its page; --daemon: the fetcher held "
                                      "for good): install, remove, status, run")
    add_service_arguments(s)
    s.set_defaults(func=cmd_service)
    return p


ACTIONS = ("serve", "status", "request", "pass", "cancel", "host")


def stored_ticker(symbol: str) -> str:
    """The name a symbol is stored under, from the text typed (TSE:7203: 7203.T; EUR/USD: EURUSD),
    or the text itself when the library cannot read it (the fetcher then says why)."""
    try:
        return lib.resolve(symbol).ticker
    except ValueError:
        return symbol.strip().upper()


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ACTIONS:  # `liminal-integrator serve`: the fetcher's actions at the top
        argv = ["fetcher", *argv]
    args = build_parser().parse_args(argv)
    try:
        apply_instance(args)
    except ValueError as e:
        print(e)
        return 2
    settings = lib.config.load_settings()
    return args.func(args, settings)
