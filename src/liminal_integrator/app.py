"""The integrator as an app of the frame (liminal_libs.apps.App; the user, 2026-11-04: every app has one
master icon, the integrator's the fetcher's scroll; 2026-11-06: "the app itself (either chart or integrator)
has plugin ABC as well"; "the plugin ABC will enumerate attached plugins and their API"): what holds the
integrator's plugins, the stock-data plugins (the feeds and publishers: SYSTEM "integrator"), and its
login, the one authorization interface they read their keys through. The fetcher's process holds one
(Fetcher.app, attached at the host's start) and so does the page's (service.py hands it to the chart
app's serve_integrator, which answers /api/interface with it and passes it the routes it does not
answer itself); the page and the data API are still the chart app's code in this process (lib.page());
the App base takes the server over at 0.3.0.

1.15.0 (Monday list item 30, step 4; the user, 2026-11-24: "through the rust interface", then "inheritance bro";
2026-11-25: the instance forms move to the platform's Databases section, the platform the only writer of instance
settings): IntegratorApp inherits the library's platform core (liminal_libs.apps.platform.Platform), not the whole
liminal-platform app. It needs the database plugins (PLATFORM_NEEDS), holds them in its own process with its own login
and opens its databases through them there (the data path pays no hop), and it is not the running platform: it reads
the instance settings and never writes them. A change to an instance is asked of the running platform over liminal-net
(its node platform-databases: Platform.change_on_platform), never over HTTP; with no platform running it is said, in
words, and nothing is started.

Its own routes (`api`): the databases it keeps, for its page's Databases view (the user, 2026-11-07:
"the integrator will have stats for the databases themselves"): `GET /api/databases` the list, `GET
/api/databases/detail?id=` one database (databases.py), its figures and nobody else's; the database plugins'
instances (1.12.0; the user, 2026-11-15: "for the integrator i need plugins for each type of database ... each
instance in the plugin has it's own configuration how it's shared, ports, permissions etc"): `GET
/api/databases/plugins` every engine's plugin with its instances (the library's overview, which offers no change here),
`POST /api/databases/instances` a test answered here, a change carried to the platform (instances.py, the library's
names); and the auditors (1.13.0; the user, 2026-11-18: "an auditor plugin, for auditing sources and maintaining the
integrity of the feeds; for the integrator"): `GET /api/auditor` where they stand (their policy, the fetch cache, the
last sweep, the findings), `POST /api/auditor/run` an audit or a sweep asked for now (auditors.py).

1.16.1 (Monday list item 17; the user, 2026-11-16: "for all apps, and all plugins, there should be an external api
tab, and an internal api tab"): its own two views, GET /api/app/apis, the first entry of its page's Plugins view
("This app"). Its Internal API lists its routes (routes(): the data API's, as the charts list them, then its own six,
routes.py), the platform it links and a few words of its own (INTERNAL_NOTES); its External API the cards of what its
own code associates with (apis.py)."""
from __future__ import annotations

import threading
from http import HTTPStatus
from pathlib import Path

from . import lib
from .routes import ROUTES, unanswered

# what a change to an instance is answered with while no platform runs (503): where it is made, and why not now
PLATFORM_DOWN = "change this on the platform's Databases section; the platform is not running"


class IntegratorApp(lib.Platform):
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
    # the platform core it inherits (1.15.0): the database plugins attached by this need; not the writer (PLATFORM_WRITER
    # stays False): the running platform alone changes instance settings
    PLATFORM_NEEDS = ("database",)
    # its own Internal API (1.16.1, Monday list item 17; liminal-libs 1.63.0's App, GET /api/app/apis): its own routes
    # (routes()), the app it links and a few words of its own
    ROUTES = ROUTES
    LINKED = (
        ("platform", "linked over liminal-net (its node platform-databases), never over HTTP and never started from "
                     "here: a change to a database plugin's instance is asked of the running platform, the one writer "
                     "of their settings; with none running it is said, in words"),
    )
    INTERNAL_NOTES = (
        "The page and the data API at the integrator's port are the charts' code, served in this process (liminal-charts' "
        "serve_integrator): their routes are listed first, as the charts list them, and what they leave to this app "
        "(its databases, its auditors, the frame's own routes) is answered here.",
        "The fetcher runs in a host process of its own (liminal_libs.host's fetcher): the page reaches it over its pipe "
        "alone, never over HTTP, while a page is in touch (or for good as the daemon). That process holds an "
        "IntegratorApp of its own (Fetcher.app), with no port.",
        "The login is an object of the login class held here, the integrator its superclass: its page and its API under "
        "/login/ at the integrator's own port, no port of its own. The plugins read their keys through it.",
        "The AI assistants are the platform's: they are not attached here, and their entries on the Plugins view are "
        "read from the plugin objects the registry loaded, nothing of them called.",
    )

    def __init__(self, log=print, login: lib.Login | None = None, db_path: Path | None = None, *, node_factory=None):
        # A daemon has no browser session: the user environment variables stand in for the login (the
        # machine's user is the signed-in user) until it can hold a session of its own.
        # node_factory: liminal_net.Node (the default), or a test's stand-in: what reaches the platform's node
        super().__init__(log=log, login=login if login is not None else lib.EnvironmentLogin(), node_factory=node_factory)
        self.db_path = Path(db_path) if db_path is not None else None  # its database: the data folder is beside it
        self._databases = None
        self._databases_lock = threading.Lock()
        self.fetcher = None  # the fetcher whose app this is (fetcher.Fetcher sets it): one of its parts

    def parts(self) -> tuple:
        """What it includes besides its login and its plugins, told a signal before the plugins (1.14.0, Monday list
        item 38): the fetcher in the fetcher host's process, so its loop ends and its writes are secured (the runs let
        go, the extras and the auditors ended, its store closed) before a plugin it uses is let go. None elsewhere
        (the page's frame in the service)."""
        return (self.fetcher,) if self.fetcher is not None else ()

    def routes(self) -> tuple:
        """Its own routes as its Internal API lists them (1.16.1): the page's data API's first, as the charts list them
        (lib.page_routes: its /api/plugins, /api/interface and /api/ui come before the frame's), with the frame's writes
        its server does not answer said so (routes.unanswered), then its own (ROUTES), each (method, path) once. A
        charts from before 0.2.10: its own alone."""
        data, not_answered = lib.page_routes()
        out, seen = [], set()
        for row in (*data, *unanswered(not_answered), *self.ROUTES):
            if (row[0], row[1]) not in seen:
                seen.add((row[0], row[1]))
                out.append(row)
        return tuple(out)

    def attach_plugins(self, only: str | None = None) -> list[str]:
        """Every plugin of this system the registry loaded (`only`: another system), attached here with
        this app's login; the names attached (a plugin another app holds is left alone). 1.15.0: with this system's,
        the kinds the platform core needs (Platform.attach_needs: the database plugins, platform plugins since
        liminal-libs 1.90.0), attached once."""
        out = lib.attach_registry(self, only=self.SYSTEM if only is None else only)
        if only is None:
            out += [name for name in self.attach_needs() if name not in out]
        return out

    @property
    def databases(self):
        """The Databases view's figures for this integrator's data folder (made at the first ask: a
        process that never shows the view never lists the folder)."""
        from .databases import Databases

        with self._databases_lock:
            if self._databases is None:
                from . import instances

                folder = self.db_path.parent if self.db_path is not None else lib.layout.data_dir()
                # (with the instances its database plugins hold outside the folder: listed with the folder's own)
                self._databases = Databases(folder, log=self.log, extra=lambda: instances.elsewhere(self))
            return self._databases

    def instance_change(self, body: dict) -> dict:
        """One form of the page answered (POST /api/databases/instances, 1.15.0): a test here, in this process (an
        instance opened for reading, as the data path opens it); a change asked of the running platform through its
        node, the one writer (Platform.change_on_platform), and its refusal back as it was said there (Asked: its
        status, its words, what accepts it). With no platform running, said in words (Refused 503, PLATFORM_DOWN) and
        nothing started or written here. A change made there is listed here at once (the folder's figures forgotten)."""
        from . import instances

        body = body if isinstance(body, dict) else {}
        if instances.text_of(body, "action") not in instances.CHANGES:
            return self.instances_asked(body)
        try:
            out = self.change_on_platform(body)
        except instances.Asked:
            raise
        except lib.Refused as e:
            if e.status != HTTPStatus.SERVICE_UNAVAILABLE:
                raise
            self.log(f"{self.NAME}: {instances.text_of(body, 'plugin')} {instances.text_of(body, 'action')} not asked: "
                     f"{e.reason}")
            raise lib.Refused(HTTPStatus.SERVICE_UNAVAILABLE, PLATFORM_DOWN) from None
        forget = getattr(self.databases, "forget", None)
        if callable(forget):
            forget()
        return out

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
        if method == "GET" and path == "/api/databases/plugins":
            return 200, self.databases_overview()  # the platform core's: the library's overview, no change offered here
        if method == "POST" and path == "/api/databases/instances":
            from . import instances

            try:
                return 200, self.instance_change(body if isinstance(body, dict) else {})
            except instances.Asked as e:
                # the plugin's words and what accepts its refusal (the page's second question): the frame's handler of
                # a Refused would send only {"error"}
                return e.status, e.answer()
        if method == "GET" and path == "/api/auditor":
            from . import auditors

            return 200, auditors.overview(self)
        if method == "POST" and path == "/api/auditor/run":
            from . import auditors

            return 200, auditors.ask(self, body if isinstance(body, dict) else {})
        return super().api(handler, method, path, query, body)
