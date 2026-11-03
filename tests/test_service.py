"""The integrator's service (service.py): its page from the user's logon with the fetcher running
while a page is in touch, or as a daemon (the user, 2026-11-02: "the integrator needs to be able to
run autonomously in a 'daemon' mode") the fetcher held for good and started again when it ends;
`serve` runs the same in the foreground. Nothing is installed or started here: the page's front and
the fetcher stand in as fakes."""
from __future__ import annotations

import threading
import time
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

from liminal_integrator import cli, lib, service


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


def _fake_front(served: list):
    """A serve_front (the app's front) that records what it was asked and stays up until told to stop."""
    def serve_front(db_path, port=8765, open_browser=True, log=None, mode="chart", stop=None):
        served.append({"db_path": db_path, "port": port, "open_browser": open_browser, "mode": mode})
        stop.wait()
        served.append("down")
    return serve_front


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
    monkeypatch.setattr(lib, "front", lambda: _fake_front(served))
    monkeypatch.setattr(lib, "attach_fetcher", _no_hold)
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "8791")
    monkeypatch.setattr(service, "CHECK_SECONDS", 0.01)
    lines: list[str] = []
    stop = threading.Event()
    threading.Timer(0.3, stop.set).start()
    assert service.run(settings, lines.append, stop) == 0
    assert served[0] == {"db_path": settings.db_path, "port": 8791, "open_browser": False, "mode": "fetcher"}
    _down(served)
    assert any("page at http://127.0.0.1:8791/" in m for m in lines) and lines[-1].startswith("service: ended")
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
    monkeypatch.setattr(lib, "front", lambda: _fake_front(served))
    monkeypatch.setenv("LIMINAL_FETCHER_PORT", "8791")
    monkeypatch.setattr(service, "RESTART_SECONDS", 0.01)
    monkeypatch.setattr(service, "CHECK_SECONDS", 0.01)
    lines: list[str] = []
    stop = threading.Event()
    threading.Timer(0.5, stop.set).start()
    assert service.run(settings, lines.append, stop, daemon=True) == 0
    assert made[0] is None and made[1].detached is False and made[1].lives < 0  # it ended on its own
    assert made[2].detached  # the one held when the service stopped: let go
    assert served and served[0]["mode"] == "fetcher" and served[0]["port"] == 8791  # its page is up as well
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
    monkeypatch.setattr(service, "unit_path", lambda: tmp_path / "user" / "liminal-integrator.service")
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
    monkeypatch.setattr(service, "run", lambda s, log, stop=None, open_browser=False, port=None, daemon=False:
                        ran.append((open_browser, port, daemon)) or 0)
    monkeypatch.setattr(lib.config, "load_settings", lambda *a, **kw: settings)
    assert cli.main(["serve", "--no-browser"]) == 0 and ran[-1] == (False, None, False)
    assert cli.main([]) == 0 and ran[-1] == (True, None, False)  # the default: in the browser, on the fetcher's port
    assert cli.main(["serve", "--port", "0", "--no-browser", "--daemon"]) == 0 and ran[-1] == (False, 0, True)
    hosted: list = []
    monkeypatch.setattr(cli.fetcher, "run_host", lambda settings, log=None, port=None, rescan=None: hosted.append(port))
    assert cli.main(["host", "--port", "8792"]) == 0 and hosted == [8792]
    assert cli.main(["host"]) == 0 and hosted == [8792, None]  # the port of its own (page_port)
