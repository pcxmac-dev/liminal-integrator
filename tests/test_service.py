"""The integrator's service (service.py): its page and data API served in its own process from the
user's logon with the fetcher running while a page is in touch (the user, 2026-11-03: "for the
webserver / ports, i just integrator, and charts"), or as a daemon (2026-11-02: "the integrator needs
to be able to run autonomously in a 'daemon' mode") the fetcher held for good and started again when
it ends; `serve` runs the same in the foreground. Nothing is installed or started here: the page
server and the fetcher stand in as fakes."""
from __future__ import annotations

import os
import threading
import time
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

import pytest

from liminal_integrator import cli, fetcher, lib, service


class FakeAttachment:
    def __init__(self, lives):
        self.lives, self.detached, self.host_pid = lives, False, 4242

    def alive(self):
        if self.detached:
            return False
        self.lives -= 1
        return self.lives >= 0

    def detach(self):
        self.detached = True


def _settings(tmp_path):
    return replace(lib.config.load_settings(env={}, env_file=None), db_path=tmp_path / "liminal.db")


def _fake_page(served: list):
    """A serve_integrator (the charts app's page server) that records what it was asked and stays up
    until told to stop."""
    def serve_integrator(settings, port, *, link, open_browser=False, log=None, stop=None, rescan=False, reload_settings=None,
                         until_quiet=False, frame=None):
        served.append({"db_path": settings.db_path, "port": port, "open_browser": open_browser, "link": type(link).__name__,
                       "until_quiet": until_quiet, "frame": type(frame).__name__ if frame is not None else None})
        stop.wait()
        served.append("down")
    return serve_integrator


def _down(served: list) -> None:
    end = time.monotonic() + 2
    while "down" not in served and time.monotonic() < end:
        time.sleep(0.01)
    assert served[-1] == "down"  # the page's server was told to stop with the service


def _no_hold(db_path, log=print):
    raise AssertionError("the service held the fetcher without --daemon")


def test_the_service_keeps_the_page_and_the_fetcher_runs_only_while_a_page_is_in_touch(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    served: list = []
    monkeypatch.setattr(lib, "page", lambda: _fake_page(served))
    monkeypatch.setattr(lib, "attach_fetcher", _no_hold)
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "8791")
    monkeypatch.setattr(service, "CHECK_SECONDS", 0.01)
    lines: list[str] = []
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()
    assert service.run(settings, lines.append, stop) == 0
    assert served[0] == {"db_path": settings.db_path, "port": 8791, "open_browser": False, "link": "FetcherLink", "until_quiet": False,
                         "frame": "IntegratorApp"}  # the page's hold on the integrator's plugins
    _down(served)
    assert any("page and data API at http://127.0.0.1:8791/" in m for m in lines) and lines[-1].startswith("service: ended")
    # until quiet (what the chart front starts for itself): the page server is told so
    served.clear()
    stop = threading.Event()
    threading.Timer(0.1, stop.set).start()
    assert service.run(settings, lines.append, stop, until_quiet=True) == 0 and served[0]["until_quiet"] is True
    _down(served)
    # in the foreground (`serve`): its page in the browser, on the port asked
    served.clear()
    stop = threading.Event()
    threading.Timer(0.1, stop.set).start()
    assert service.run(settings, lines.append, stop, open_browser=True, port=8792) == 0
    assert served[0]["open_browser"] is True and served[0]["port"] == 8792
    _down(served)
    # no page (the port off) and no hold: nothing to run
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "off")
    assert service.run(settings, lines.append, threading.Event()) == 2 and "nothing to run" in lines[-1]


def test_the_daemon_holds_the_fetcher_and_starts_it_again_when_it_ends(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    made: list = []
    answers = [None, FakeAttachment(lives=2), FakeAttachment(lives=99)]  # none answers, one that ends, one that stays

    def attach_fetcher(db_path, log=print):
        assert db_path == settings.db_path
        att = answers.pop(0) if answers else FakeAttachment(lives=99)
        made.append(att)
        return att
    monkeypatch.setattr(lib, "attach_fetcher", attach_fetcher)
    served: list = []
    monkeypatch.setattr(lib, "page", lambda: _fake_page(served))
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "8791")
    monkeypatch.setattr(service, "RESTART_SECONDS", 0.01)
    monkeypatch.setattr(service, "CHECK_SECONDS", 0.01)
    lines: list[str] = []
    stop = threading.Event()
    threading.Timer(0.5, stop.set).start()
    assert service.run(settings, lines.append, stop, daemon=True) == 0
    assert made[0] is None and made[1].detached is False and made[1].lives < 0  # it ended on its own
    assert made[2].detached  # the one held when the service stopped: let go
    assert served and served[0]["port"] == 8791 and served[0]["until_quiet"] is False  # its page is up as well; never until quiet
    _down(served)
    assert any("no fetcher answered" in m for m in lines) and any("the fetcher ended" in m for m in lines)
    assert lines[-1].startswith("service: ended")
    # held with no page at all (the port off): the fetcher alone
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "none")
    served.clear()
    stop = threading.Event()
    threading.Timer(0.1, stop.set).start()
    assert service.run(settings, lines.append, stop, daemon=True) == 0 and served == [] and made[-1].detached


def test_the_windows_task_and_the_systemd_unit(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "8785")
    cmd = service.command()
    assert cmd[1:] == ["-m", "liminal_integrator", "service", "run"] and Path(cmd[0]).name.startswith("python")
    assert service.command(daemon=True)[1:] == ["-m", "liminal_integrator", "service", "run", "--daemon"]
    # the task through the Task Scheduler cmdlets (schtasks refuses a logon trigger without elevation)
    install = service.task_args("install")
    assert install[:4] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"] and len(install) == 5
    script = install[-1]
    assert script.startswith("$ErrorActionPreference = 'Stop'; try { ") and script.endswith("exit 1 }")
    assert f"-Execute '{cmd[0]}' -Argument '-m liminal_integrator service run'" in script
    assert "New-ScheduledTaskTrigger -AtLogOn -User" in script and "Register-ScheduledTask -TaskName 'LiminalIntegrator'" in script
    assert "-ExecutionTimeLimit ([TimeSpan]::Zero)" in script and "-MultipleInstances IgnoreNew" in script
    assert "-Argument '-m liminal_integrator service run --daemon'" in service.task_args("install", daemon=True)[-1]
    assert "Unregister-ScheduledTask -TaskName 'LiminalIntegrator' -Confirm:$false" in service.task_args("remove")[-1]
    assert "Get-ScheduledTask -TaskName 'LiminalIntegrator'" in service.task_args("status")[-1]
    assert "Start-ScheduledTask -TaskName 'LiminalIntegrator'" in service.task_args("start")[-1]
    assert service._ps("it's") == "'it''s'"  # a quote in a path doubled, as PowerShell wants it
    unit = service.unit_text(settings.db_path)
    assert "ExecStart=" in unit and "-m liminal_integrator service run\n" in unit and "while a page is in touch" in unit
    assert f"Environment=LIMINAL_DB={settings.db_path}" in unit
    assert "Restart=on-failure" in unit and "WantedBy=default.target" in unit
    held = service.unit_text(settings.db_path, daemon=True)
    assert "service run --daemon\n" in held and "held for good" in held
    for secret in ("KEY", "TOKEN", "PASSWORD"):
        assert secret not in (unit + held).upper().replace("LIMINAL_DB", "")  # no key ever written into it
    # install and remove run the platform's commands, without a console window
    calls: list[list[str]] = []
    monkeypatch.setattr(service, "_call", lambda args: calls.append(args) or 0)
    monkeypatch.setattr(service.sys, "platform", "win32")
    lines: list[str] = []
    assert service.install(settings, lines.append) == 0
    assert "Register-ScheduledTask" in calls[0][-1] and "Start-ScheduledTask" in calls[1][-1] and "at your logon, as you" in lines[-1]
    assert "its page at http://127.0.0.1:8785/" in lines[-1] and "while a page is in touch" in lines[-1]
    assert service.install(settings, lines.append, daemon=True) == 0
    assert "service run --daemon'" in calls[-2][-1] and "held for good" in lines[-1]
    assert service.remove(settings, lines.append) == 0 and "Unregister-ScheduledTask" in calls[-1][-1]
    assert service.status(settings, lines.append) == 0 and "Get-ScheduledTask" in calls[-1][-1]
    monkeypatch.setattr(service, "_call", lambda args: 1)  # the Task Scheduler refused: said, not started
    assert service.install(settings, lines.append) == 1 and "could not be registered" in lines[-1]
    monkeypatch.setattr(service, "_call", lambda args: calls.append(args) or 0)
    monkeypatch.setattr(service.sys, "platform", "linux")
    monkeypatch.setattr(service, "unit_path", lambda name="": tmp_path / "user" / "liminal-integrator.service")
    calls.clear()
    assert service.install(settings, lines.append) == 0
    assert (tmp_path / "user" / "liminal-integrator.service").read_text(encoding="utf-8") == unit
    assert calls == [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", "liminal-integrator"]]
    assert "enable-linger" in lines[-1] and "keyring" in lines[-1]
    assert service.install(settings, lines.append, daemon=True) == 0
    assert (tmp_path / "user" / "liminal-integrator.service").read_text(encoding="utf-8") == held
    assert service.remove(settings, lines.append) == 0 and not (tmp_path / "user" / "liminal-integrator.service").exists()
    assert calls[-2] == ["systemctl", "--user", "disable", "--now", "liminal-integrator"]
    monkeypatch.setattr(service.sys, "platform", "darwin")
    assert service.install(settings, lines.append) == 2 and "only Windows" in lines[-1]


def test_the_service_command(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    seen: list = []
    for name in ("run", "install", "remove", "status"):
        monkeypatch.setattr(service, name, lambda s, log, _n=name, **kw: seen.append((_n, kw.get("daemon"))) or 0)
    for action in ("install", "remove", "status", "run"):
        assert cli.cmd_service(Namespace(action=action, daemon=False), settings) == 0
    assert seen == [("install", False), ("remove", None), ("status", None), ("run", False)]
    monkeypatch.setattr(lib.config, "load_settings", lambda *a, **kw: settings)
    assert cli.main(["service", "status"]) == 0 and seen[-1] == ("status", None)
    assert cli.main(["service", "run", "--daemon"]) == 0 and seen[-1] == ("run", True)
    assert cli.main(["service", "install", "--daemon"]) == 0 and seen[-1] == ("install", True)


def test_serve_runs_the_service_here_with_its_page_in_the_browser(tmp_path, monkeypatch):
    """`liminal-integrator serve` (the user, 2026-11-02: "a way to run it from the browser like the
    other liminals"): the service's process in the foreground, its page in the browser unless told
    not to, on the port asked, the fetcher held for good with --daemon; `host` runs a fetcher here."""
    settings = _settings(tmp_path)
    ran: list = []
    monkeypatch.setattr(service, "run", lambda s, log, stop=None, open_browser=False, port=None, daemon=False, until_quiet=False:
                        ran.append((open_browser, port, daemon, until_quiet)) or 0)
    monkeypatch.setattr(lib.config, "load_settings", lambda *a, **kw: settings)
    assert cli.main(["serve", "--no-browser"]) == 0 and ran[-1] == (False, None, False, False)
    assert cli.main([]) == 0 and ran[-1] == (True, None, False, False)  # the default: in the browser, on the integrator's port
    assert cli.main(["serve", "--port", "0", "--no-browser", "--daemon"]) == 0 and ran[-1] == (False, 0, True, False)
    assert cli.main(["serve", "--no-browser", "--until-quiet"]) == 0 and ran[-1] == (False, None, False, True)
    hosted: list = []
    monkeypatch.setattr(cli.fetcher, "run_host", lambda settings, log=None, port=None, rescan=None: hosted.append(port))
    assert cli.main(["host", "--port", "8792"]) == 0 and hosted == [8792]
    assert cli.main(["host"]) == 0 and hosted == [8792, None]  # the port of its own (page_port)


def test_an_integrator_of_its_own_has_its_name_database_port_and_plugins(tmp_path, monkeypatch):
    """The user, 2026-11-03: "multiple integrators can address databases". `--name` installs or serves
    an integrator of its own: the task LiminalIntegrator-NAME (the unit liminal-integrator-NAME) running
    `service run --name NAME --db ...` with its port and plugins baked in; its database store/data/NAME/
    unless --db; every process it starts inherits its name, database and plugins (LIMINAL_INTEGRATOR_NAME,
    LIMINAL_DB, LIMINAL_PLUGINS_LOADED: cli.apply_instance)."""
    settings = _settings(tmp_path)
    db = tmp_path / "paper" / "liminal.db"
    cmd = service.command(daemon=True, name="paper", db_path=db, port=8786, plugins="twse,tiingo")
    assert cmd[1:] == ["-m", "liminal_integrator", "service", "run", "--name", "paper", "--db", str(db), "--port", "8786",
                       "--plugins", "twse,tiingo", "--daemon"]
    assert service.command()[1:] == ["-m", "liminal_integrator", "service", "run"]  # the one and only, as before
    assert service.task_name("paper") == "LiminalIntegrator-paper" and service.task_name() == "LiminalIntegrator"
    script = service.task_args("install", name="paper", db_path=db, port=8786, plugins="none")[-1]
    assert "-TaskName 'LiminalIntegrator-paper'" in script and f"--name paper --db {db} --port 8786 --plugins none'" in script
    assert "-TaskName 'LiminalIntegrator-paper'" in service.task_args("remove", name="paper")[-1]
    assert "-TaskName 'LiminalIntegrator'" in service.task_args("status")[-1]
    assert service.unit_path("paper").name == "liminal-integrator-paper.service" and service.unit_path().name == "liminal-integrator.service"
    unit = service.unit_text(db, daemon=False, name="paper", port=8786, plugins="twse")
    assert f"Environment=LIMINAL_DB={db}" in unit and "service run --name paper --port 8786 --plugins twse\n" in unit
    assert "Description=Liminal integrator paper:" in unit
    # installed as one of its own: the task named for it, its database named outright, its page at its port
    calls: list[list[str]] = []
    monkeypatch.setattr(service, "_call", lambda args: calls.append(args) or 0)
    monkeypatch.setattr(service.sys, "platform", "win32")
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "8785")
    lines: list[str] = []
    assert service.install(settings, lines.append, name="paper", port=8786, plugins="twse", db_path=db) == 0
    assert "'LiminalIntegrator-paper'" in calls[0][-1] and f"--db {db} --port 8786 --plugins twse'" in calls[0][-1]
    assert "Start-ScheduledTask -TaskName 'LiminalIntegrator-paper'" in calls[1][-1]
    assert "the task LiminalIntegrator-paper runs `liminal-integrator service run --name paper" in lines[-1]
    assert "its page at http://127.0.0.1:8786/" in lines[-1] and "`service remove --name paper`" in lines[-1]
    assert service.install(settings, lines.append, name="paper") == 0  # no --db: the settings' database, named outright
    assert f"--name paper --db {settings.db_path}'" in calls[-2][-1]
    assert service.remove(settings, lines.append, name="paper") == 0 and "'LiminalIntegrator-paper'" in calls[-1][-1]
    assert service.status(settings, lines.append, name="paper") == 0 and "'LiminalIntegrator-paper'" in calls[-1][-1]
    monkeypatch.setattr(service.sys, "platform", "linux")
    monkeypatch.setattr(service, "unit_path", lambda name="": tmp_path / "user" / f"{service.unit_name(name)}.service")
    assert service.install(settings, lines.append, name="paper", port=8786) == 0
    assert "--name paper --port 8786\n" in (tmp_path / "user" / "liminal-integrator-paper.service").read_text(encoding="utf-8")
    assert calls[-1] == ["systemctl", "--user", "enable", "--now", "liminal-integrator-paper"]
    # the name is a task's, a unit's and a folder's
    for bad in ("", "a b", "x/y", "-x", "n" * 41):
        with pytest.raises(ValueError):
            fetcher.check_name(bad)
    assert fetcher.check_name("paper-2_b") == "paper-2_b"
    assert fetcher.instance_db("paper") == lib.layout.data_dir() / "paper" / "liminal.db"
    # the command line applies them to this process, and so to the ones it starts
    for var in (fetcher.NAME_VAR, "LIMINAL_DB", lib.SELECTION_VAR):
        monkeypatch.setenv(var, "")  # restored (deleted) after
    monkeypatch.setattr(lib.config, "load_settings", lambda *a, **kw: replace(settings, db_path=Path(os.environ["LIMINAL_DB"])))
    ran: list = []
    monkeypatch.setattr(service, "run", lambda s, log, stop=None, open_browser=False, port=None, daemon=False, until_quiet=False:
                        ran.append((s.db_path, port, daemon)) or 0)
    assert cli.main(["serve", "--name", "paper", "--port", "8786", "--plugins", "none", "--no-browser"]) == 0
    assert os.environ[fetcher.NAME_VAR] == "paper" and fetcher.instance_name() == "paper"
    assert os.environ["LIMINAL_DB"] == str(lib.layout.data_dir() / "paper" / "liminal.db") == str(ran[-1][0])
    assert ran[-1][1:] == (8786, False) and os.environ[lib.SELECTION_VAR] == "none" and lib.providers() == {}
    assert cli.main(["serve", "--name", "x y"]) == 2  # not a name
    assert cli.main(["serve", "--name", "paper", "--db", str(db), "--plugins", "all", "--no-browser"]) == 0
    assert os.environ["LIMINAL_DB"] == str(db) and lib.SELECTION_VAR not in os.environ and lib.providers()
    seen: list = []
    monkeypatch.setattr(service, "install", lambda s, log, **kw: seen.append(kw) or 0)
    assert cli.main(["service", "install", "--name", "paper", "--port", "8786", "--plugins", "twse", "--daemon"]) == 0
    assert seen[-1] == {"daemon": True, "name": "paper", "port": 8786, "plugins": "twse", "db_path": None}
    assert cli.main(["service", "install", "--db", str(db)]) == 0 and seen[-1]["db_path"] == db and seen[-1]["name"] == ""
    monkeypatch.setattr(service, "run", lambda s, log, **kw: seen.append(kw) or 0)
    assert cli.main(["service", "run", "--name", "paper", "--port", "8786"]) == 0 and seen[-1] == {"daemon": False, "port": 8786}
    assert fetcher.plugins_line({"selection": "twse,nobody", "loaded": ["twse"], "leftOut": ["massive"], "unknown": ["nobody"]}) \
        == "plugins loaded: twse (twse,nobody asked for); left out: massive; unknown: nobody"
    assert fetcher.plugins_line({"selection": "all", "loaded": []}) == "plugins loaded: none"


def test_the_link_holds_the_fetcher_while_a_page_is_in_touch_and_asks_it_over_the_pipe(tmp_path, monkeypatch):
    """FetcherLink: the page server's hold on the fetcher host (the user, 2026-11-03: two listeners,
    the fetcher host with no HTTP of its own): attached at a page's first touch (started if none
    answers), its status, a wake and a pass over the pipe, let go once quiet, attached again after."""
    class Pipe(FakeAttachment):
        def __init__(self):
            super().__init__(lives=99)
            self.asked: list[dict] = []

        def ask(self, **what):
            self.asked.append(what)
            if self.detached:
                raise EOFError("gone")
            return {"pid": 4242, "busy": False} if what.get("status") else {"ok": True}

    pipes: list[Pipe] = []

    def attach_fetcher(db_path, log=print):
        assert db_path == tmp_path / "liminal.db"
        pipes.append(Pipe())
        return pipes[-1]
    monkeypatch.setattr(lib, "attach_fetcher", attach_fetcher)
    lines: list[str] = []
    link = service.FetcherLink(tmp_path / "liminal.db", lines.append)
    assert not link.connected
    link.touch()
    assert link.connected and len(pipes) == 1 and any("connected to the fetcher (pid 4242)" in m for m in lines)
    link.touch()
    assert len(pipes) == 1  # held: not attached again
    assert link.status() == {"pid": 4242, "busy": False} and pipes[0].asked[-1] == {"status": True}
    link.wake_up()
    link.ask_pass()
    assert pipes[0].asked[-2:] == [{"wake": True}, {"pass": True}]
    pipes[0].detach()  # the fetcher gone: the next ask attaches (and starts) again
    assert link.status() == {"pid": 4242, "busy": False} and len(pipes) == 2
    assert link.let_go() is True and pipes[1].detached and not link.connected and link.let_go() is False
    # quiet: no page in touch for a while, the fetcher let go, and the server told when asked (until quiet)
    link.touch()
    monkeypatch.setattr(link, "quiet_seconds", lambda: 0.05)
    monkeypatch.setattr(service, "QUIET_CHECK_SECONDS", 0.01)
    stop = threading.Event()
    quiet: list = []
    threading.Thread(target=link.watch_quiet, args=(stop, lambda: quiet.append(1) or stop.set()), daemon=True).start()
    assert stop.wait(5) and quiet == [1] and pipes[2].detached and not link.connected
    assert any("quiet: no page in touch" in m for m in lines)
    # no fetcher answers at all: nothing to ask; the page reads the status file then
    monkeypatch.setattr(lib, "attach_fetcher", lambda db_path, log=print: None)
    assert link.status() is None and not link.connected
    link.wake_up()  # nothing to wake: no error
