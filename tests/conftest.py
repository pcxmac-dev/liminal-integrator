"""Guards copied from liminal's tests/conftest.py: tests never read the user's real keys, never
start a process or a host, and never attach to one (the feeds' runs are fakes a test gives)."""
from __future__ import annotations

import subprocess

import pytest


@pytest.fixture(autouse=True)
def no_saved_keys(monkeypatch):
    """Tests never read the user's saved keys (their user environment variables)."""
    from liminal_lib import config
    from liminal_lib.sources.registry import variables

    monkeypatch.setattr(config, "saved_user_keys", lambda: {})
    for name in variables():
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def no_found_limits(monkeypatch):
    """Nor the limits kept from the user's last capability scans (in their database)."""
    from liminal_lib.sources import registry

    monkeypatch.setattr(registry, "found_limits", lambda name, settings: [])


@pytest.fixture(autouse=True)
def no_processes_or_hosts(monkeypatch, tmp_path):
    """Tests never start a process (the extras, a host) nor attach to a host: a test that wants a
    feed's run gives a fake (lib.feed_run)."""
    from liminal_lib import host

    from liminal_integrator import fetcher, lib

    def no_spawn(args, **kw):
        raise AssertionError(f"a test started a process: {args}")
    monkeypatch.setenv("LIMINAL_IPC_DIR", str(tmp_path / "ipc"))
    monkeypatch.setattr(host, "start_host", lambda name, db_path: no_spawn(["host", name]))
    monkeypatch.setattr(host, "attach_or_start", lambda name, db_path, log=print: None)
    monkeypatch.setattr(lib, "attach_fetcher", lambda db_path, log=print: None)
    monkeypatch.setattr(lib, "feed_run", lambda name, db_path, log=print: None)
    monkeypatch.setattr(lib, "history_run", lambda db_path, log=print: None)
    monkeypatch.setattr(fetcher.subprocess, "Popen", no_spawn)
    monkeypatch.setattr(subprocess, "Popen", no_spawn)
