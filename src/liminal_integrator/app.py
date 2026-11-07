"""The integrator as an app of the frame (liminal_libs.apps.App; the user, 2026-11-04: every app has one
master icon, the integrator's the fetcher's scroll; 2026-11-06: "the app itself (either chart or integrator)
has plugin ABC as well"; "the plugin ABC will enumerate attached plugins and their API"): what holds the
integrator's plugins, the stock-data plugins (the feeds and publishers: SYSTEM "integrator"), and its
login, the one authorization interface they read their keys through. The fetcher's process holds one
(Fetcher.app, attached at the host's start) and so does the page's (service.py hands it to the chart
app's serve_integrator, which answers /api/interface with it); the page and the data API are still the
chart app's code in this process (lib.page()); the App base takes the server over at 0.3.0."""
from __future__ import annotations

from . import lib


class IntegratorApp(lib.App):
    NAME = "integrator"
    TITLE = "Liminal Integrator"
    ICON = "scroll"  # the fetcher's icon on the rail (icons.js)
    PORT = 8785
    PORT_VAR = "LIMINAL_FETCHER_PORT"
    SYSTEM = "integrator"  # the plugins it holds

    def __init__(self, log=print, login: lib.Login | None = None):
        # A daemon has no browser session: the user environment variables stand in for the login (the
        # machine's user is the signed-in user) until it can hold a session of its own.
        super().__init__(log=log, login=login if login is not None else lib.EnvironmentLogin())

    def attach_plugins(self, only: str | None = None) -> list[str]:
        """Every plugin of this system the registry loaded (`only`: another system), attached here with
        this app's login; the names attached (a plugin another app holds is left alone)."""
        return lib.attach_registry(self, only=self.SYSTEM if only is None else only)
