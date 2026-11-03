"""The integrator's service: its page kept at its port with the fetcher running while a page is in
touch, or, as a daemon, the fetcher held for good so it collects what it can on its own; in the
foreground with `serve`, from your logon once installed.

The user, 2026-11-02: "i need a way to run it from the browser like the other liminals", and "the
integrator needs to be able to run autonomously in a 'daemon' mode". So the fetcher's page is kept
at http://127.0.0.1:8785/ like the chart app's at 8765 (lib.front(): the app's front in mode
"fetcher"; the fetcher, fetcher.py's host `fetcher`, attached and started if none answers when a
page comes, let go once none has been in touch for a while; its own page then takes a free port,
learnt from it). "Only while I use it" (2026-11-01) stays the default: between pages nothing runs.
With `--daemon` the fetcher is held for good, started again once it ends, and its standing passes
go on on their own (every feed's run once new data can exist, the closed months' copy, the extras);
between passes it holds no store and no plugin's run.

- Windows: a Task Scheduler task at your logon, as you (TASK_NAME), running `liminal-integrator
  service run` with pythonw (no window). As you it sees your user environment variables, where the
  keys live; a service under a service account would not, unless you stored your password with it
  yourself.
- Linux: a systemd user unit (UNIT_NAME, ~/.config/systemd/user), enabled and started; with
  lingering (`loginctl enable-linger`) it runs without a login. A user unit does not inherit your
  shell's variables: the keys need a home it can read at boot (your choice: the OS keyring,
  systemd's encrypted credentials), never a file this program writes.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from . import fetcher, lib

TASK_NAME = "LiminalIntegrator"
UNIT_NAME = "liminal-integrator"
RESTART_SECONDS = 10.0  # the daemon starts the fetcher again this long after it ended
CHECK_SECONDS = 5.0
Log = Callable[[str], None]


def python_quiet() -> Path:
    """The interpreter the service runs with: pythonw where it exists (no console window)."""
    exe = Path(sys.executable)
    quiet = exe.with_name("pythonw.exe")
    return quiet if os.name == "nt" and quiet.exists() else exe


def command(daemon: bool = False) -> list[str]:
    """What the installed service runs: `liminal-integrator service run`, `--daemon` for the
    fetcher held for good."""
    return [str(python_quiet()), "-m", "liminal_integrator", "service", "run", *(["--daemon"] if daemon else [])]


def page_url(port: int | None = None) -> str | None:
    """Where the service keeps the fetcher's page (fetcher.page_port: LIMINAL_FETCHER_PORT, or the
    port given). None: no page at all; a free port is named in the log once taken."""
    port = fetcher.page_port() if port is None else port
    if port is None:
        return None
    return f"http://127.0.0.1:{port}/" if port else "a free port (logs/liminal.log says which)"


def _does(daemon: bool) -> str:
    page = f"its page at {page_url()}" if page_url() else "no page (LIMINAL_FETCHER_PORT is off)"
    return page + (", the fetcher held for good (the daemon: it collects what it can on its own)" if daemon
                   else ", the fetcher while a page is in touch")


# -- Windows: a scheduled task at logon ---------------------------------------------------------
def task_args(action: str, daemon: bool = False) -> list[str]:
    """The schtasks line for install, remove, status or start."""
    if action == "install":
        line = " ".join(f'"{a}"' if " " in a else a for a in command(daemon))
        return ["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "ONLOGON", "/TR", line, "/F"]
    if action == "remove":
        return ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    if action == "start":
        return ["schtasks", "/Run", "/TN", TASK_NAME]
    return ["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"]


# -- Linux: a systemd user unit ------------------------------------------------------------------
def unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{UNIT_NAME}.service"


def unit_text(db_path: Path | None = None, daemon: bool = False) -> str:
    """The unit: `liminal-integrator service run`, started again on failure, with the database's
    path (no key: those are yours to give the unit)."""
    env = f"Environment=LIMINAL_DB={db_path}\n" if db_path else ""
    what = ("the fetcher held for good, collecting what it can on its own, and its page" if daemon
            else "the fetcher's page, and the fetcher while a page is in touch")
    return (
        "[Unit]\n"
        f"Description=Liminal integrator: {what}\n"
        "After=network-online.target\n\n"
        "[Service]\n"
        f"ExecStart={' '.join(command(daemon))}\n"
        f"{env}"
        "Restart=on-failure\n"
        f"RestartSec={RESTART_SECONDS:g}\n"
        "KillSignal=SIGINT\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _call(args: list[str]) -> int:
    return subprocess.call(args, **lib.proc.no_window())


def install(settings, log: Log = print, daemon: bool = False) -> int:
    runs = f"`liminal-integrator service run{' --daemon' if daemon else ''}`"
    if sys.platform == "win32":
        code = _call(task_args("install", daemon))
        if code == 0:
            _call(task_args("start"))
            log(f"service: the task {TASK_NAME} runs {runs} at your logon, as you (your user environment variables, "
                f"the keys among them, are its); started now: {_does(daemon)}. `service remove` takes it away.")
        return code
    if sys.platform.startswith("linux"):
        path = unit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(unit_text(settings.db_path, daemon), encoding="utf-8")
        code = _call(["systemctl", "--user", "daemon-reload"]) or _call(["systemctl", "--user", "enable", "--now", UNIT_NAME])
        log(f"service: the unit {path} is enabled and started: {_does(daemon)}. To run it without a login: "
            f"`loginctl enable-linger {os.environ.get('USER', '')}`. The unit does not see your shell's variables: give "
            "it the keys through the OS keyring or systemd's encrypted credentials (your choice), never a file this "
            "program writes.")
        return code
    log("service: only Windows (a task at logon) and Linux (a systemd user unit) are supported; "
        "`liminal-integrator serve` runs it here meanwhile")
    return 2


def remove(settings, log: Log = print) -> int:
    if sys.platform == "win32":
        return _call(task_args("remove"))
    if sys.platform.startswith("linux"):
        code = _call(["systemctl", "--user", "disable", "--now", UNIT_NAME])
        path = unit_path()
        if path.exists():
            path.unlink()
        _call(["systemctl", "--user", "daemon-reload"])
        return code
    log("service: nothing installed on this platform")
    return 0


def status(settings, log: Log = print) -> int:
    if sys.platform == "win32":
        return _call(task_args("status"))
    if sys.platform.startswith("linux"):
        return _call(["systemctl", "--user", "status", UNIT_NAME, "--no-pager"])
    log("service: nothing installed on this platform")
    return 0


# -- the service's own process -------------------------------------------------------------------
def run(settings, log: Log = print, stop: threading.Event | None = None, open_browser: bool = False,
        port: int | None = None, daemon: bool = False) -> int:
    """The service's process: the fetcher's page at its port (lib.front(); `port`, or
    LIMINAL_FETCHER_PORT; in the browser when `open_browser`: `serve`), the fetcher attached when
    a page comes and let go once none has been in touch for a while, and with `daemon` the fetcher
    held for good: attached (started if none answers), attached again once it ends. Until this
    process is told to stop (SIGINT, SIGTERM, Ctrl+C: the page down, the fetcher let go)."""
    stop = stop or threading.Event()

    def ending(signum, frame) -> None:
        stop.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, ending)
            except (ValueError, OSError):
                pass  # not the main thread (a test): stopped by its event
    port = fetcher.page_port() if port is None else port
    if port is None and not daemon:
        log("service: LIMINAL_FETCHER_PORT is off (no page) and the fetcher is not held (--daemon): nothing to run")
        return 2
    if port is not None:
        threading.Thread(target=lib.front(), kwargs={"db_path": settings.db_path, "port": port, "open_browser": open_browser,
                                                     "log": log, "mode": "fetcher", "stop": stop},
                         name="service-page", daemon=True).start()
        log(f"service: the fetcher's page at {page_url(port)}; the fetcher runs while a page is in touch")
    if not daemon:
        log("service: up until told to stop (Ctrl+C, a stop)")
        while not stop.wait(CHECK_SECONDS):
            pass
        log("service: ended; the page is down, the fetcher let go")
        return 0
    log("service: the daemon holds the fetcher for good (it collects what it can on its own; Ctrl+C or a stop lets it go)")
    while not stop.is_set():
        att = lib.attach_fetcher(settings.db_path, log=log)
        if att is None:
            log(f"service: no fetcher answered; asked again in {RESTART_SECONDS:g} s")
            stop.wait(RESTART_SECONDS)
            continue
        log(f"service: the fetcher is up (pid {att.host_pid})")
        while not stop.is_set() and att.alive():
            stop.wait(CHECK_SECONDS)
        if stop.is_set():
            att.detach()
            break
        log(f"service: the fetcher ended; started again in {RESTART_SECONDS:g} s")
        stop.wait(RESTART_SECONDS)
    log("service: ended; the fetcher let go")
    return 0
