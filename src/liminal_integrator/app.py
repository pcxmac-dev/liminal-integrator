"""The integrator as an app of the frame (liminal_libs.apps.App; the user, 2026-11-04: every app has one
master icon, the integrator's the fetcher's scroll; 2026-11-06: "the app itself (either chart or integrator)
has plugin ABC as well"; "the plugin ABC will enumerate attached plugins and their API"): what holds the
integrator's plugins, the stock-data plugins (the feeds and publishers: SYSTEM "integrator"), and its
login, the one authorization interface they read their keys through. The fetcher's process holds one
(Fetcher.app, attached at the host's start) and so does the page's (service.py hands it to the chart
app's serve_integrator, which answers /api/interface with it and passes it the routes it does not
answer itself); the page and the data API are still the chart app's code in this process (lib.page());
the App base takes the server over at 0.3.0.

Its own routes (`api`): the databases it keeps, for its page's Databases view (the user, 2026-11-07:
"the integrator will have stats for the databases themselves, the platform only cares about
hardware"): `GET /api/databases` the list, `GET /api/databases/detail?id=` one database (databases.py)."""
from __future__ import annotations

import threading
from http import HTTPStatus
from pathlib import Path

from . import lib


class IntegratorApp(lib.App):
    NAME = "integrator"
    TITLE = "Liminal Integrator"
    ICON = "scroll"  # the fetcher's icon on the rail (icons.js)
    PORT = 8785
    PORT_VAR = "LIMINAL_FETCHER_PORT"
    SYSTEM = "integrator"  # the plugins it holds
    # the login the integrator inherits (1.9.0; the user, 2026-11-14: "the platform and integrator inherit the login
    # function, they are separate login instances, class vs object"): an object of the login class this frame holds
    # (liminal-libs App.login_object), its users the integrator's own, answered under /login/ at the integrator's port by
    # its page's server (liminal-charts serve_integrator), the page its sign-in until signed in there; the data API is
    # not behind it (the chart app's front reads it). LIMINAL_INTEGRATOR_LOGIN "none" or "off": none.
    LOGIN, LOGIN_VAR = True, "LIMINAL_INTEGRATOR_LOGIN"

    def __init__(self, log=print, login: lib.Login | None = None, db_path: Path | None = None):
        # A daemon has no browser session: the user environment variables stand in for the login (the
        # machine's user is the signed-in user) until it can hold a session of its own.
        super().__init__(log=log, login=login if login is not None else lib.EnvironmentLogin())
        self.db_path = Path(db_path) if db_path is not None else None  # its database: the data folder is beside it
        self._databases = None
        self._databases_lock = threading.Lock()

    def attach_plugins(self, only: str | None = None) -> list[str]:
        """Every plugin of this system the registry loaded (`only`: another system), attached here with
        this app's login; the names attached (a plugin another app holds is left alone)."""
        return lib.attach_registry(self, only=self.SYSTEM if only is None else only)

    @property
    def databases(self):
        """The Databases view's figures for this integrator's data folder (made at the first ask: a
        process that never shows the view never lists the folder)."""
        from .databases import Databases

        with self._databases_lock:
            if self._databases is None:
                folder = self.db_path.parent if self.db_path is not None else lib.layout.data_dir()
                self._databases = Databases(folder, log=self.log)
            return self._databases

    def api(self, handler, method: str, path: str, query: dict, body: dict | None):
        if method == "GET" and path == "/api/databases":
            return 200, self.databases.overview()
        if method == "GET" and path == "/api/databases/detail":
            ident = query.get("id") or ""
            if not ident:
                raise lib.Refused(HTTPStatus.BAD_REQUEST, "which database: ?id=")
            try:
                return 200, self.databases.detail(ident)
            except LookupError as e:
                raise lib.Refused(HTTPStatus.NOT_FOUND, str(e)) from None
        return super().api(handler, method, path, query, body)
