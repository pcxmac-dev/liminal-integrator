"""The integrator's service: its page kept at its port with the fetcher running while a page is in
touch, or, as a daemon, the fetcher held for good so it collects what it can on its own; in the
foreground with `serve`, from your logon once installed.

The user, 2026-11-02: "i need a way to run it from the browser like the other liminals", and "the
integrator needs to be able to run autonomously in a 'daemon' mode"; 2026-11-03: "for the webserver
/ ports, i just integrator, and charts". So this process serves the integrator's page and the data
API itself at http://127.0.0.1:8785/ like the chart app's front at 8765 (lib.page(): the charts
app's serve_integrator, reading the data here), and holds the fetcher (fetcher.py's host `fetcher`,
over its pipe alone) through a FetcherLink: attached, and started if none answers, at the first
request of a page, let go once none has been in touch for a while; its status, a wake and a pass
go over the pipe. Two listeners on the machine, the fetcher host none. "Only while I use it"
(2026-11-01) stays the default: between pages nothing runs. `serve --until-quiet` ends this process
too once no page has been in touch for a while: what the chart app's front starts for itself when
nothing answers at the port.
With `--daemon` the fetcher is held for good, started again once it ends, and its standing passes
go on on their own (every feed's run once new data can exist, the closed months' copy, the extras);
between passes it holds no store and no plugin's run.

- Windows: a Task Scheduler task at your logon, as you (TASK_NAME), running `liminal-integrator
  service run` with pythonw (no window), registered through the Task Scheduler cmdlets: `schtasks
  /Create /SC ONLOGON` answers "Access is denied" without elevation, while a task triggered by your
  own logon is yours to register. As you it sees your user environment variables, where the keys
  live; a service under a service account would not, unless you stored your password with it
  yourself.
- Linux: a systemd user unit (UNIT_NAME, ~/.config/systemd/user), enabled and started; with
  lingering (`loginctl enable-linger`) it runs without a login. A user unit does not inherit your
  shell's variables: the keys need a home it can read at boot (your choice: the OS keyring,
  systemd's encrypted credentials), never a file this program writes.

An integrator of its own (`--name`, the user, 2026-11-03: "multiple integrators can address
databases"): its task LiminalIntegrator-<name> (its unit liminal-integrator-<name>), running
`service run --name <name> --db <its database> [--port N] [--plugins ...]`: its own database, page
port and plugins, installed, removed and asked beside the one and only.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from . import fetcher, lib

TASK_NAME = "LiminalIntegrator"
UNIT_NAME = "liminal-integrator"
RESTART_SECONDS = 10.0  # the daemon starts the fetcher again this long after it ended
CHECK_SECONDS = 5.0
QUIET_SECONDS = 120.0  # no page in touch for this long: the fetcher let go (LIMINAL_QUIET_SECONDS)
QUIET_CHECK_SECONDS = 15.0
Log = Callable[[str], None]


class FetcherLink:
    """This process's hold on the fetcher host over the pipe, for the page and data API served here
    (lib.page()): attached at a page's first request (`touch`; the fetcher started if none answers),
    let go once no page has been in touch for QUIET_SECONDS (`watch_quiet`; the daemon's own hold
    keeps the fetcher up regardless); its status, a wake and a pass asked over the pipe (what the
    page server asks of a fetcher: `status`, `wake_up`, `ask_pass`)."""

    def __init__(self, db_path: Path, log: Log = print):
        self.db_path = Path(db_path)
        self.log = log
        self._lock = threading.Lock()
        self._att = None
        self._last_contact = time.monotonic()
        self._woken = False

    def quiet_seconds(self) -> float:
        try:
            return float(lib.config.setting("LIMINAL_QUIET_SECONDS") or QUIET_SECONDS)
        except ValueError:
            return QUIET_SECONDS

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._att is not None

    def touch(self) -> None:
        """A page is in touch: the fetcher attached (started if none answers) and kept."""
        with self._lock:
            self._last_contact = time.monotonic()
            self._woken = True
            self._attach_locked()

    def _attach_locked(self):
        if self._att is not None:
            try:
                if self._att.alive():
                    return self._att
            except Exception:  # noqa: BLE001 - a broken pipe is a fetcher gone
                pass
            self._att = None
        self._att = lib.attach_fetcher(self.db_path, log=self.log)
        if self._att is not None:
            self.log(f"the integrator's page is connected to the fetcher (pid {self._att.host_pid})")
        return self._att

    def _ask(self, **what):
        with self._lock:
            self._last_contact = time.monotonic()
            self._woken = True
            att = self._attach_locked()
            if att is None:
                return None
            try:
                return att.ask(**what)
            except (OSError, EOFError, ValueError):
                self._att = None  # gone: attached (and started) again at the next ask
                return None

    def status(self) -> dict | None:
        """The fetcher's status over the pipe; None when none answers (the page reads the file then)."""
        answer = self._ask(status=True)
        return answer if isinstance(answer, dict) else None

    def wake_up(self) -> None:
        self._ask(wake=True)

    def ask_pass(self) -> None:
        self._ask(**{"pass": True})

    def let_go(self) -> bool:
        """The fetcher let go (it ends once nobody holds it). Whether it was held."""
        with self._lock:
            att, self._att = self._att, None
        if att is None:
            return False
        try:
            att.detach()
        except Exception:  # noqa: BLE001 - gone already
            pass
        return True

    def watch_quiet(self, stop: threading.Event | None = None, on_quiet: Callable[[], None] | None = None) -> None:
        """Lets the fetcher go once no page has been in touch for quiet_seconds (a thread), and
        calls `on_quiet` then (serve --until-quiet: the server ends)."""
        stop = stop or threading.Event()
        while not stop.wait(QUIET_CHECK_SECONDS):
            with self._lock:
                due = self._woken and time.monotonic() - self._last_contact >= self.quiet_seconds()
            if due:
                held = self.let_go()
                self._woken = False
                if held:
                    self.log(f"quiet: no page in touch for {self.quiet_seconds():g} s; the fetcher is let go")
                if on_quiet is not None:
                    on_quiet()


def python_quiet() -> Path:
    """The interpreter the service runs with: pythonw where it exists (no console window)."""
    exe = Path(sys.executable)
    quiet = exe.with_name("pythonw.exe")
    return quiet if os.name == "nt" and quiet.exists() else exe


def task_name(name: str = "") -> str:
    """The task's name: LiminalIntegrator, or LiminalIntegrator-<name> for an integrator of its own."""
    return f"{TASK_NAME}-{name}" if name else TASK_NAME


def unit_name(name: str = "") -> str:
    """The unit's name: liminal-integrator, or liminal-integrator-<name>."""
    return f"{UNIT_NAME}-{name}" if name else UNIT_NAME


def command(daemon: bool = False, name: str = "", db_path: Path | None = None, port: int | None = None,
            plugins: str | None = None) -> list[str]:
    """What the installed service runs: `liminal-integrator service run`, with `--name` and `--db`
    for an integrator of its own (its database named outright), `--port` and `--plugins` when
    given, `--daemon` for the fetcher held for good."""
    out = [str(python_quiet()), "-m", "liminal_integrator", "service", "run"]
    if name:
        out += ["--name", name]
    if db_path is not None:
        out += ["--db", str(db_path)]
    if port is not None:
        out += ["--port", str(port)]
    if plugins is not None:
        out += ["--plugins", plugins]
    return out + (["--daemon"] if daemon else [])


def page_url(port: int | None = None) -> str | None:
    """Where the service keeps the fetcher's page (fetcher.page_port: LIMINAL_FETCHER_PORT, or the
    port given). None: no page at all; a free port is named in the log once taken."""
    port = fetcher.page_port() if port is None else port
    if port is None:
        return None
    return f"http://127.0.0.1:{port}/" if port else "a free port (logs/liminal.log says which)"


def _does(daemon: bool, port: int | None = None) -> str:
    url = page_url(port)
    page = f"its page at {url}" if url else "no page (LIMINAL_FETCHER_PORT is off)"
    return page + (", the fetcher held for good (the daemon: it collects what it can on its own)" if daemon
                   else ", the fetcher while a page is in touch")


# -- Windows: a scheduled task at logon ---------------------------------------------------------
def _ps(text: str) -> str:
    """`text` as a PowerShell single-quoted string."""
    return "'" + text.replace("'", "''") + "'"


def task_script(action: str, daemon: bool = False, name: str = "", db_path: Path | None = None, port: int | None = None,
                plugins: str | None = None) -> str:
    """The PowerShell (the Task Scheduler cmdlets) for install, remove, status or start; the task
    named for the integrator (task_name)."""
    task = _ps(task_name(name))
    if action == "install":
        exe, *args = command(daemon, name, db_path, port, plugins)
        return (f"$a = New-ScheduledTaskAction -Execute {_ps(exe)} -Argument {_ps(' '.join(args))}; "
                "$t = New-ScheduledTaskTrigger -AtLogOn -User \"$env:USERDOMAIN\\$env:USERNAME\"; "
                "$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew "
                "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries; "
                f"Register-ScheduledTask -TaskName {task} -Action $a -Trigger $t -Settings $s -Force | Out-Null")
    if action == "remove":
        return f"Unregister-ScheduledTask -TaskName {task} -Confirm:$false"
    if action == "start":
        return f"Start-ScheduledTask -TaskName {task}"
    return (f"Get-ScheduledTask -TaskName {task} | Format-List TaskName, State, "
            "@{n='Command';e={$_.Actions[0].Execute + ' ' + $_.Actions[0].Arguments}}; "
            f"Get-ScheduledTaskInfo -TaskName {task} | Format-List LastRunTime, LastTaskResult, NextRunTime")


def task_args(action: str, daemon: bool = False, name: str = "", db_path: Path | None = None, port: int | None = None,
              plugins: str | None = None) -> list[str]:
    """The command line for install, remove, status or start: PowerShell running task_script,
    failing (exit 1) when a cmdlet does."""
    script = ("$ErrorActionPreference = 'Stop'; try { " + task_script(action, daemon, name, db_path, port, plugins)
              + " } catch { [Console]::Error.WriteLine($_.Exception.Message); exit 1 }")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]


# -- Linux: a systemd user unit ------------------------------------------------------------------
def unit_path(name: str = "") -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{unit_name(name)}.service"


def unit_text(db_path: Path | None = None, daemon: bool = False, name: str = "", port: int | None = None,
              plugins: str | None = None) -> str:
    """The unit: `liminal-integrator service run` (with the integrator's name, port and plugins),
    started again on failure, with the database's path (no key: those are yours to give the unit)."""
    env = f"Environment=LIMINAL_DB={db_path}\n" if db_path else ""
    what = ("the fetcher held for good, collecting what it can on its own, and its page" if daemon
            else "the fetcher's page, and the fetcher while a page is in touch")
    return (
        "[Unit]\n"
        f"Description=Liminal integrator{' ' + name if name else ''}: {what}\n"
        "After=network-online.target\n\n"
        "[Service]\n"
        f"ExecStart={' '.join(command(daemon, name, None, port, plugins))}\n"
        f"{env}"
        "Restart=on-failure\n"
        f"RestartSec={RESTART_SECONDS:g}\n"
        "KillSignal=SIGINT\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def _call(args: list[str]) -> int:
    return subprocess.call(args, **lib.proc.no_window())


class LogonTask:
    """Windows: the scheduled task at your logon (task_name: LiminalIntegrator, or
    LiminalIntegrator-<name> for an integrator of its own), registered, removed and asked through
    the Task Scheduler cmdlets (task_script, task_args)."""

    def __init__(self, daemon: bool = False, name: str = "", db_path: Path | None = None, port: int | None = None,
                 plugins: str | None = None):
        self.daemon, self.name, self.db_path, self.port, self.plugins = daemon, name, db_path, port, plugins

    def install(self, log: Log) -> int:
        task = task_name(self.name)
        runs = "`liminal-integrator " + " ".join(command(self.daemon, self.name, self.db_path, self.port, self.plugins)[3:]) + "`"
        code = _call(task_args("install", self.daemon, self.name, self.db_path, self.port, self.plugins))
        if code == 0:
            _call(task_args("start", name=self.name))
            log(f"service: the task {task} runs {runs} at your logon, as you (your user environment variables, "
                f"the keys among them, are its); started now: {_does(self.daemon, self.port)}. `service remove"
                f"{' --name ' + self.name if self.name else ''}` takes it away.")
        else:
            log(f"service: the task {task} could not be registered (the Task Scheduler's answer is above)")
        return code

    def remove(self, log: Log) -> int:
        return _call(task_args("remove", name=self.name))

    def status(self, log: Log) -> int:
        return _call(task_args("status", name=self.name))


class UserUnit:
    """Linux: the systemd user unit (unit_name, unit_path), written with the database's path
    (unit_text), enabled and started; removed with its file."""

    def __init__(self, db_path: Path | None = None, daemon: bool = False, name: str = "", port: int | None = None,
                 plugins: str | None = None):
        self.db_path, self.daemon, self.name, self.port, self.plugins = db_path, daemon, name, port, plugins

    def install(self, log: Log) -> int:
        path = unit_path(self.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(unit_text(self.db_path, self.daemon, self.name, self.port, self.plugins), encoding="utf-8")
        code = (_call(["systemctl", "--user", "daemon-reload"])
                or _call(["systemctl", "--user", "enable", "--now", unit_name(self.name)]))
        log(f"service: the unit {path} is enabled and started: {_does(self.daemon, self.port)}. To run it without a "
            f"login: `loginctl enable-linger {os.environ.get('USER', '')}`. The unit does not see your shell's variables: "
            "give it the keys through the OS keyring or systemd's encrypted credentials (your choice), never a file this "
            "program writes.")
        return code

    def remove(self, log: Log) -> int:
        code = _call(["systemctl", "--user", "disable", "--now", unit_name(self.name)])
        path = unit_path(self.name)
        if path.exists():
            path.unlink()
        _call(["systemctl", "--user", "daemon-reload"])
        return code

    def status(self, log: Log) -> int:
        return _call(["systemctl", "--user", "status", unit_name(self.name), "--no-pager"])


class Service:
    """The integrator's service: installed at your logon on this platform (LogonTask on Windows, a
    UserUnit on Linux; `installer`), removed, asked for its status, or run here (`run`: its page,
    and the fetcher while a page is in touch, or held for good as the daemon). An integrator of
    its own has a `name` (its task or unit named for it), `port` and `plugins` baked into what the
    service runs, and its database named outright (`db_path`: the one given, else the settings').
    The module's functions of the same names are these, for the command line."""

    def __init__(self, settings, log: Log = print, daemon: bool = False, name: str = "", port: int | None = None,
                 plugins: str | None = None, db_path: Path | None = None, until_quiet: bool = False):
        self.settings, self.log, self.daemon = settings, log, daemon
        self.name, self.port, self.plugins = name, port, plugins
        self.db_path = db_path if db_path is not None else settings.db_path if name else None  # baked when named
        self.until_quiet = until_quiet  # the page server ends once no page has been in touch for a while

    @property
    def installer(self) -> "LogonTask | UserUnit | None":
        """What installs it on this platform; None where nothing can (sys.platform, when asked)."""
        if sys.platform == "win32":
            return LogonTask(self.daemon, self.name, self.db_path, self.port, self.plugins)
        if sys.platform.startswith("linux"):
            return UserUnit(self.settings.db_path, self.daemon, self.name, self.port, self.plugins)
        return None

    def install(self) -> int:
        installer = self.installer
        if installer is None:
            self.log("service: only Windows (a task at logon) and Linux (a systemd user unit) are supported; "
                     "`liminal-integrator serve` runs it here meanwhile")
            return 2
        return installer.install(self.log)

    def remove(self) -> int:
        installer = self.installer
        if installer is None:
            self.log("service: nothing installed on this platform")
            return 0
        return installer.remove(self.log)

    def status(self) -> int:
        installer = self.installer
        if installer is None:
            self.log("service: nothing installed on this platform")
            return 0
        return installer.status(self.log)

    # -- the service's own process ---------------------------------------------------------------
    def run(self, stop: threading.Event | None = None, open_browser: bool = False, port: int | None = None) -> int:
        """The service's process: the integrator's page and data API served here (lib.page(); `port`,
        or LIMINAL_FETCHER_PORT; in the browser when `open_browser`: `serve`), the fetcher attached
        through a FetcherLink when a page comes and let go once none has been in touch for a while,
        and as the daemon the fetcher held for good: attached (started if none answers), attached
        again once it ends. Until this process is told to stop (SIGINT, SIGTERM, Ctrl+C: the page
        down, the fetcher let go), or, with `until_quiet`, until no page has been in touch for a while."""
        settings, log, daemon = self.settings, self.log, self.daemon
        stop = stop or threading.Event()
        port = self.port if port is None else port
        if self.name:
            log(f"service: the integrator {self.name}, on {settings.db_path}")

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
            from .app import IntegratorApp  # the page's hold on the integrator's plugins, with their login

            link = FetcherLink(settings.db_path, log)
            threading.Thread(target=lib.page(), args=(settings, port),
                             kwargs={"link": link, "open_browser": open_browser, "log": log, "stop": stop,
                                     "rescan": not os.environ.get("LIMINAL_NO_RESCAN"), "reload_settings": lib.config.load_settings,
                                     "frame": IntegratorApp(log=log),
                                     "until_quiet": self.until_quiet and not daemon},
                             name="service-page", daemon=True).start()
            log(f"service: the integrator's page and data API at {page_url(port)}; the fetcher runs while a page is in touch"
                + ("; this server ends once no page has been in touch for a while" if self.until_quiet and not daemon else ""))
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


# -- the command line's: each a Service's --------------------------------------------------------
def install(settings, log: Log = print, daemon: bool = False, name: str = "", port: int | None = None,
            plugins: str | None = None, db_path: Path | None = None) -> int:
    return Service(settings, log, daemon, name, port, plugins, db_path).install()


def remove(settings, log: Log = print, name: str = "") -> int:
    return Service(settings, log, name=name).remove()


def status(settings, log: Log = print, name: str = "") -> int:
    return Service(settings, log, name=name).status()


def run(settings, log: Log = print, stop: threading.Event | None = None, open_browser: bool = False,
        port: int | None = None, daemon: bool = False, until_quiet: bool = False) -> int:
    """The service's process here (Service.run): `serve`, `service run` (its name, database and
    plugins applied to the process already: cli.apply_instance); `until_quiet`: `serve
    --until-quiet`, the server ending once no page has been in touch for a while."""
    return Service(settings, log, daemon, fetcher.instance_name(), until_quiet=until_quiet).run(stop, open_browser, port)
