"""The integrator's command line: `liminal-integrator serve|status|request|pass|cancel|host` and
`liminal-integrator service install|remove|status|run`, `--daemon` on serve, install and run for
the fetcher held for good. The app's own command line answers the same (`python -m liminal fetcher
...`, `python -m liminal service ...`), through here."""
from __future__ import annotations

import argparse
import json

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
            print(f"fetcher: pid {status.get('pid')}, {'busy' if status.get('busy') else 'idle'}, page {status.get('page') or 'none'}, "
                  f"clients {status.get('clients')}, last pass {status.get('lastPass') or 'never'}, "
                  f"next due {status.get('nextDue') or 'unknown'}, feeds held: {', '.join(status.get('feeds') or []) or 'none'}")
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
            rows = [store.request_put(t, kinds=args.kinds.split(","), by="cli") for t in args.symbols]
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
    if args.action == "run":
        return service.run(settings, log, daemon=daemon)
    if args.action == "install":
        return service.install(settings, log, daemon=daemon)
    if args.action == "remove":
        return service.remove(settings, log)
    return service.status(settings, log)


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


def add_service_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("action", nargs="?", default="status", choices=["install", "remove", "status", "run"])
    p.add_argument("--daemon", action="store_true",
                   help="install, run: the fetcher held for good (it collects what it can on its own); otherwise it "
                        "runs only while a page is in touch")


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


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ACTIONS:  # `liminal-integrator serve`: the fetcher's actions at the top
        argv = ["fetcher", *argv]
    args = build_parser().parse_args(argv)
    settings = lib.config.load_settings()
    return args.func(args, settings)
