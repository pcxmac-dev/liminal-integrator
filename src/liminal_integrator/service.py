"""The fetcher as a service, by your decision: it then updates what it can while you are away.

The user, 2026-11-01: "for the plugins i would like to be able to run them as services on linux or
windows so that in they update what they can". The same day's "Only while I use it" stays the
default: nothing runs unless this service is installed, which is your decision (`liminal-integrator
service install`), and the service is nothing but a client that holds the fetcher (fetcher.py: the
host `fetcher`) for good, starting it again if it ends. Between passes the fetcher holds no store
and no plugin's run.

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

from . import lib

TASK_NAME = "LiminalFetcher"
UNIT_NAME = "liminal-fetcher"
RESTART_SECONDS = 10.0  # the fetcher started again this long after it ended
CHECK_SECONDS = 5.0
Log = Callable[[str], None]


def python_quiet() -> Path:
    """The interpreter the service runs with: pythonw where it exists (no console window)."""
    exe = Path(sys.executable)
    quiet = exe.with_name("pythonw.exe")
    return quiet if os.name == "nt" and quiet.exists() else exe


def command() -> list[str]:
    return [str(python_quiet()), "-m", "liminal_integrator", "service", "run"]


# -- Windows: a scheduled task at logon ---------------------------------------------------------
def task_args(action: str) -> list[str]:
    """The schtasks line for install, remove, status or start."""
    if action == "install":
        line = " ".join(f'"{a}"' if " " in a else a for a in command())
        return ["schtasks", "/Create", "/TN", TASK_NAME, "/SC", "ONLOGON", "/TR", line, "/F"]
    if action == "remove":
        return ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    if action == "start":
        return ["schtasks", "/Run", "/TN", TASK_NAME]
    return ["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"]


# -- Linux: a systemd user unit ------------------------------------------------------------------
def unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{UNIT_NAME}.service"


def unit_text(db_path: Path | None = None) -> str:
    """The unit: `liminal-integrator service run`, started again on failure, with the database's
    path (no key: those are yours to give the unit)."""
    env = f"Environment=LIMINAL_DB={db_path}\n" if db_path else ""
    return (
        "[Unit]\n"
        "Description=Liminal fetcher: collects and serves the market data while you are away\n"
        "After=network-online.target\n\n"
        "[Service]\n"
        f"ExecStart={' '.join(command())}\n"
        f"{env}"
        "Restart=on-failure\n"
        f"RestartSec={RESTART_SECONDS:g}\n"
        "KillSignal=SIGINT\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _call(args: list[str]) -> int:
    return subprocess.call(args, **lib.proc.no_window())


def install(settings, log: Log = print) -> int:
    if sys.platform == "win32":
        code = _call(task_args("install"))
        if code == 0:
            _call(task_args("start"))
            log(f"service: the task {TASK_NAME} runs `liminal-integrator service run` at your logon, as you (your user "
                "environment variables, the keys among them, are its); started now. `service remove` takes it away.")
        return code
    if sys.platform.startswith("linux"):
        path = unit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(unit_text(settings.db_path), encoding="utf-8")
        code = _call(["systemctl", "--user", "daemon-reload"]) or _call(["systemctl", "--user", "enable", "--now", UNIT_NAME])
        log(f"service: the unit {path} is enabled and started. To run it without a login: `loginctl enable-linger "
            f"{os.environ.get('USER', '')}`. The unit does not see your shell's variables: give it the keys through "
            "the OS keyring or systemd's encrypted credentials (your choice), never a file this program writes.")
        return code
    log("service: only Windows (a task at logon) and Linux (a systemd user unit) are supported; "
        "`liminal-integrator serve` holds the fetcher here meanwhile")
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
def run(settings, log: Log = print, stop: threading.Event | None = None) -> int:
    """Hold the fetcher for good: attached (started if none answers), attached again once it
    ends, until this process is told to stop (SIGINT, SIGTERM: the fetcher let go)."""
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
    log("service: holding the fetcher (it updates what it can; Ctrl+C or a stop lets it go)")
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
