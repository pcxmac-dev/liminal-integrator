"""The fetcher as a service (service.py): the user's decision to run it unattended; a client that
holds the fetcher for good and starts it again when it ends. Nothing is installed or started here."""
from __future__ import annotations

import threading
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


def test_the_service_holds_the_fetcher_and_starts_it_again_when_it_ends(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    made: list = []
    answers = [None, FakeAttachment(lives=2), FakeAttachment(lives=99)]  # none answers, one that ends, one that stays

    def attach_fetcher(db_path, log=print):
        assert db_path == settings.db_path
        att = answers.pop(0) if answers else FakeAttachment(lives=99)
        made.append(att)
        return att
    monkeypatch.setattr(lib, "attach_fetcher", attach_fetcher)
    monkeypatch.setattr(service, "RESTART_SECONDS", 0.01)
    monkeypatch.setattr(service, "CHECK_SECONDS", 0.01)
    lines: list[str] = []
    stop = threading.Event()
    threading.Timer(0.5, stop.set).start()
    assert service.run(settings, lines.append, stop) == 0
    assert made[0] is None and made[1].detached is False and made[1].lives < 0  # it ended on its own
    assert made[2].detached  # the one held when the service stopped: let go
    assert any("no fetcher answered" in m for m in lines) and any("the fetcher ended" in m for m in lines)
    assert lines[-1].startswith("service: ended")


def test_the_windows_task_and_the_systemd_unit(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    cmd = service.command()
    assert cmd[1:] == ["-m", "liminal_integrator", "service", "run"] and Path(cmd[0]).name.startswith("python")
    install = service.task_args("install")
    assert install[:4] == ["schtasks", "/Create", "/TN", "LiminalFetcher"] and "/SC" in install and "ONLOGON" in install
    assert install[install.index("/TR") + 1].endswith("-m liminal_integrator service run") and install[-1] == "/F"
    assert service.task_args("remove") == ["schtasks", "/Delete", "/TN", "LiminalFetcher", "/F"]
    assert service.task_args("status")[:2] == ["schtasks", "/Query"] and service.task_args("start")[1] == "/Run"
    unit = service.unit_text(settings.db_path)
    assert "ExecStart=" in unit and "-m liminal_integrator service run" in unit
    assert f"Environment=LIMINAL_DB={settings.db_path}" in unit
    assert "Restart=on-failure" in unit and "WantedBy=default.target" in unit
    for secret in ("KEY", "TOKEN", "PASSWORD"):
        assert secret not in unit.upper().replace("LIMINAL_DB", "")  # no key ever written into it
    # install and remove run the platform's commands, without a console window
    calls: list[list[str]] = []
    monkeypatch.setattr(service, "_call", lambda args: calls.append(args) or 0)
    monkeypatch.setattr(service.sys, "platform", "win32")
    lines: list[str] = []
    assert service.install(settings, lines.append) == 0
    assert calls[0][1] == "/Create" and calls[1][1] == "/Run" and "at your logon, as you" in lines[-1]
    assert service.remove(settings, lines.append) == 0 and calls[-1][1] == "/Delete"
    assert service.status(settings, lines.append) == 0 and calls[-1][1] == "/Query"
    monkeypatch.setattr(service.sys, "platform", "linux")
    monkeypatch.setattr(service, "unit_path", lambda: tmp_path / "user" / "liminal-fetcher.service")
    calls.clear()
    assert service.install(settings, lines.append) == 0
    assert (tmp_path / "user" / "liminal-fetcher.service").read_text(encoding="utf-8") == unit
    assert calls == [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", "liminal-fetcher"]]
    assert "enable-linger" in lines[-1] and "keyring" in lines[-1]
    assert service.remove(settings, lines.append) == 0 and not (tmp_path / "user" / "liminal-fetcher.service").exists()
    assert calls[-2] == ["systemctl", "--user", "disable", "--now", "liminal-fetcher"]
    monkeypatch.setattr(service.sys, "platform", "darwin")
    assert service.install(settings, lines.append) == 2 and "only Windows" in lines[-1]


def test_the_service_command(tmp_path, monkeypatch):
    settings = _settings(tmp_path)
    seen: list[str] = []
    for name in ("run", "install", "remove", "status"):
        monkeypatch.setattr(service, name, lambda s, log, _n=name: seen.append(_n) or 0)
    for action in ("install", "remove", "status", "run"):
        assert cli.cmd_service(Namespace(action=action), settings) == 0
    assert seen == ["install", "remove", "status", "run"]
    monkeypatch.setattr(lib.config, "load_settings", lambda *a, **kw: settings)
    assert cli.main(["service", "status"]) == 0 and seen[-1] == "status"
