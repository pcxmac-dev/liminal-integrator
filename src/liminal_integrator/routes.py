"""The integrator's own routes, as its Internal API lists them beside the frame's (1.16.1, Monday list item 17;
liminal-libs 1.63.0's internal.py; the user, 2026-11-16: "for all apps, and all plugins, there should be an external
api tab, and an internal api tab"; 2026-11-17: "all plugins all apps").

Two tables answer at the integrator's port, in this one process. The page and the data API are the charts' code
(lib.page(): liminal-charts' serve_integrator), and its rows are the charts' own (liminal-charts 0.2.10's gui/routes.py
DATA_ROUTES, read through lib.page_routes()), with the frame's writes its server does not answer said so
(unanswered). What the data API leaves to its frame is answered by IntegratorApp.api: ROUTES, the integrator's own
six. IntegratorApp.routes lists the data API's first (its /api/plugins, /api/interface and /api/ui come before the
frame's rows of the same routes), then these.

Each row is (method, path, what it is, its class, who asks it), as liminal_libs.internal.FRAME_ROUTES: `{...}` is a
part that varies; the class is read, change, ask or stream; who asks it is "page" here. Plain tuples: nothing is
imported with them but the frame's table. tests/test_routes.py holds ROUTES to IntegratorApp.api: a route added there
without its row here fails it."""
from __future__ import annotations

try:  # liminal-libs 1.63.0: the frame's own routes (every floor of the integrator has them; an older library: none)
    from liminal_libs.internal import FRAME_ROUTES
except ImportError:  # pragma: no cover - a library from before 1.63.0
    FRAME_ROUTES = ()

ROUTES = (
    ("GET", "/api/databases", "the Databases view: every SQLite and DuckDB file of the data folder and Liminal's "
                              "MongoDB, their sizes, growth and last writes (databases.py; nothing opened to list them)",
     "read", "page"),
    ("GET", "/api/databases/detail", "one database's own figures (?id=): its tables and their rows, opened read-only "
                                     "for the moment they are read", "read", "page"),
    ("GET", "/api/databases/plugins", "every database plugin with its instances, as the platform core lists them, and "
                                      "writer: false (a change is made on the platform's Databases section)", "read",
     "page"),
    ("POST", "/api/databases/instances", "a database plugin's form: a test answered here, in this process; a change "
                                         "asked of the running platform over liminal-net (503 when none runs)",
     "change", "page"),
    ("GET", "/api/auditor", "the auditors: their policy, the fetch cache by state and size, the last sweep, the "
                            "findings, the audits asked for (auditors.py)", "read", "page"),
    ("POST", "/api/auditor/run", "an audit of a symbol or a sweep asked for now, taken by the fetcher (auditors.py)",
     "change", "page"),
)

# what is said of the frame's writes the integrator's page server does not answer (POST /api/app/stop ...): its
# service ends on its stop event (liminal-stop-integrator, which liminal-signal sets: service.stop_event), or on
# SIGINT and SIGTERM
UNANSWERED = ("not answered by the integrator's page server (404): its service ends on its stop event "
              "(liminal-stop-integrator, which liminal-signal sets), or on SIGINT or SIGTERM; the frame's words: ")


def unanswered(paths) -> tuple:
    """The frame's writes the data API does not answer (`paths`: (method, path) pairs, the charts' NOT_ANSWERED_PATHS),
    each said so in the integrator's words, the frame's own after them (its class and who asks it the frame's); a pair
    the frame has no row of is left out."""
    out = []
    for method, path in paths:
        row = next((r for r in FRAME_ROUTES if (r[0], r[1]) == (method, path)), None)
        if row is not None:
            out.append((method, path, UNANSWERED + row[2], *row[3:5]))
    return tuple(out)
