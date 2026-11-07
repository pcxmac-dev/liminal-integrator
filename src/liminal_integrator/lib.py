"""Every call into the library goes through here (the user, 2026-11-01: "make sure that the library
calls contribute to code reuse"; "all lib calls will point to liminal-lib"): what the integrator
uses of liminal-libs, by name, and nothing of the charts app but the page and data API it serves
in its own process (page()). A library piece the integrator needs is added to liminal-libs, never
written here twice."""
from __future__ import annotations

from liminal_libs import collector, config, freshness, layout, proc, runner, sourcing  # noqa: F401
from liminal_libs import host  # noqa: F401
from liminal_libs.apps import App, EnvironmentLogin, Login, attach_registry  # noqa: F401
from liminal_libs.host import FETCHER, Host, attach_fetcher, feed_run, history_run  # noqa: F401
from liminal_libs.host import wait_for_fetcher, wait_for_requests  # noqa: F401
from liminal_libs.logs import Logger, log_to  # noqa: F401
from liminal_libs.models import is_foreign  # noqa: F401
from liminal_libs.proc import hold_until_interrupted  # noqa: F401
from liminal_libs.sessions import ET  # noqa: F401
from liminal_libs.sources import feed_closed, feed_profiles, providers, supports  # noqa: F401
from liminal_libs.sources.registry import SELECTION_VAR, plugin_fetchers, plugins_loaded, select, selection  # noqa: F401
from liminal_libs.storage import Store  # noqa: F401
from liminal_libs.storage.requests import KINDS, OPEN, STATUS_KEY, read_status, write_status  # noqa: F401
from liminal_libs.stores import history_due  # noqa: F401
from liminal_libs.symbols import resolve  # noqa: F401


def page():
    """The integrator's page and data API, served in the integrator's own process (the user,
    2026-11-03: "for the webserver / ports, i just integrator, and charts"): the chart app's
    liminal_charts.gui.server.serve_integrator, with a FetcherLink (service.py) to the fetcher host
    over the pipe. Imported when the server starts, not before (the app, liminal-charts, is the
    integrator's one dependency outside the library, for this)."""
    from liminal_charts.gui.server import serve_integrator

    return serve_integrator
