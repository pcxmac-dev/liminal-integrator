"""The integrator as an app of the frame (app.py): its plugins attached with its login, the fetcher's and
the command line's hold on it."""
from __future__ import annotations

from dataclasses import replace

from liminal_libs.apps import App, EnvironmentLogin
from liminal_libs.sources.registry import assistants, providers, publishers

from liminal_integrator import cli, fetcher, lib
from liminal_integrator.app import IntegratorApp


def test_the_integrator_holds_its_plugins_through_the_frame(tmp_path, monkeypatch, capsys):
    app = IntegratorApp(log=lambda m: None)
    assert isinstance(app, App) and isinstance(app.login, EnvironmentLogin) and (app.NAME, app.ICON, app.PORT) == ("integrator", "scroll", 8785)
    free = {n for n, p in [*providers().items(), *publishers().items()] if p.app is None or p.app is app}
    names = app.attach_plugins()
    assert set(names) == free and not (set(names) & set(assistants()))  # the stock-data plugins, never the platform's
    assert all(app.plugin(n).login is app.login and app.plugin(n).app is app for n in names)
    assert app.interface()["plugins"] == sorted(names) and set(app.plugins()) == set(names)
    for n in names:
        app.detach(n)
    assert app.plugins() == {}
    settings = replace(lib.config.load_settings(env={"MASSIVE_API_KEY": "k"}, env_file=None), db_path=tmp_path / "liminal.db")
    f = fetcher.Fetcher(settings, lambda m: None)
    assert isinstance(f.app, IntegratorApp) and f.login is f.app.login and f.app.plugins() == {}  # run_host attaches
    # the command line reads the settings through the login
    seen: list[dict] = []
    monkeypatch.setattr(lib.config, "load_settings", lambda *a, **kw: seen.append(kw) or settings)
    assert cli.main(["status"]) == 0 and isinstance(seen[0]["login"], EnvironmentLogin)
    capsys.readouterr()
