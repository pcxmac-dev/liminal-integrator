"""Every call into the library goes through here (the user, 2026-11-01: "make sure that the library
calls contribute to code reuse"; "all lib calls will point to liminal-lib"): what the integrator
uses of liminal-libs, by name, and nothing of the charts app but the page and data API it serves
in its own process (page()) and what that data API answers and asks of the plugins, for its own Internal API
(page_routes(), page_calls()). A library piece the integrator needs is added to liminal-libs, never
written here twice."""
from __future__ import annotations

from liminal_libs import auditing, claims, collector, config, freshness, layout, proc, runner, sourcing, systemd  # noqa: F401
from liminal_libs import host, lifecycle, mongo  # noqa: F401
from liminal_libs.apps import App, EnvironmentLogin, Login, Refused, attach_registry  # noqa: F401
from liminal_libs.apps.platform import Platform  # noqa: F401 - the platform core the integrator inherits (1.90.0)
from liminal_libs.host import FETCHER, Host, attach_fetcher, feed_run, history_run  # noqa: F401
from liminal_libs.host import wait_for_fetcher, wait_for_requests  # noqa: F401
from liminal_libs.logs import Logger, log_to  # noqa: F401
from liminal_libs.models import is_foreign  # noqa: F401
from liminal_libs.mounts import NotHere  # noqa: F401
from liminal_libs.proc import hold_until_interrupted  # noqa: F401
from liminal_libs.sessions import ET  # noqa: F401
from liminal_libs.sources import apis, feed_closed, feed_profiles, providers, supports  # noqa: F401
from liminal_libs.sources.registry import SELECTION_VAR, plugin_fetchers, plugins_loaded, select, selection  # noqa: F401
from liminal_libs.sources.registry import databases, errors as plugin_errors  # noqa: F401 - the database plugins (1.61.0)
from liminal_libs.sources.registry import auditors  # noqa: F401 - the auditors' plugin (1.64.0)
from liminal_libs.storage import Store, read_only, set_read_only  # noqa: F401
from liminal_libs.storage.common import Behind  # noqa: F401
from liminal_libs.storage.databases import ENGINES as DATABASE_ENGINES, Refusal  # noqa: F401
from liminal_libs.storage.link import LinkError  # noqa: F401
from liminal_libs.storage.requests import AUDIT, EVERYTHING, KINDS, OPEN, STATUS_KEY, WAITING  # noqa: F401
from liminal_libs.storage.requests import read_status, write_status  # noqa: F401
from liminal_libs.stores import history_due  # noqa: F401
from liminal_libs.stores import close_instances, forget_instances  # noqa: F401 - the instances picks name (1.91.0)
from liminal_libs.symbols import resolve  # noqa: F401


def page():
    """The integrator's page and data API, served in the integrator's own process (the user,
    2026-11-03: "for the webserver / ports, i just integrator, and charts"): the chart app's
    liminal_charts.gui.server.serve_integrator, with a FetcherLink (service.py) to the fetcher host
    over the pipe. Imported when the server starts, not before (the app, liminal-charts, is the
    integrator's one dependency outside the library, for this)."""
    from liminal_charts.gui.server import serve_integrator

    return serve_integrator


def page_routes() -> tuple:
    """What the page's data API answers, as the charts list it (liminal-charts 0.2.10's gui/routes.py): its rows in its
    chain's order, then the frame's writes it does not answer as (method, path) pairs, for the integrator's own
    Internal API (IntegratorApp.routes). Beside page(), the integrator's one other use of the charts' code, imported
    when the Internal API is asked; a charts from before 0.2.10 has no table: none, and nothing fails."""
    try:
        from liminal_charts.gui.routes import DATA_ROUTES, NOT_ANSWERED_PATHS
    except ImportError:
        return (), ()
    return tuple(DATA_ROUTES), tuple(NOT_ANSWERED_PATHS)


def page_calls() -> tuple[dict, dict]:
    """What the page's data API calls and reads on a plugin of each kind, as the charts declare it (liminal-charts
    0.2.10's ChartsApp.CALLS and ATTRIBUTES: their gui/plugins.py and gui/server.py, the code that works with the
    integrator's plugins in this process), for the integrator's own Internal API and its plugins'
    (IntegratorApp.calls_with_page). Imported when an Internal API is asked; a charts from before: none."""
    try:
        from liminal_charts.frame import ChartsApp
    except ImportError:
        return {}, {}
    calls, attributes = getattr(ChartsApp, "CALLS", {}), getattr(ChartsApp, "ATTRIBUTES", {})
    return (calls if isinstance(calls, dict) else {}), (attributes if isinstance(attributes, dict) else {})
