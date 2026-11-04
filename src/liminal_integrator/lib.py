"""Every call into the library goes through here (the user, 2026-11-01: "make sure that the library
calls contribute to code reuse"; "all lib calls will point to liminal-libs"): what the integrator
uses of liminal-libs, by name, and nothing of the app but the page it serves (page()) and the front
that keeps that page at its port (front()). A library piece the integrator needs is added to
liminal-libs, never written here twice."""
from __future__ import annotations

from liminal_libs import collector, config, freshness, layout, proc, runner, sourcing  # noqa: F401
from liminal_libs import host  # noqa: F401
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
    """The page and data API the fetcher serves: the chart app's (liminal_charts.gui.server.serve_fetcher),
    imported when a fetcher starts, not before (the app, liminal-charts, is the integrator's one
    dependency outside the library, for this)."""
    from liminal_charts.gui.server import serve_fetcher

    return serve_fetcher


def front():
    """The front that keeps the fetcher's page at its port while the fetcher comes and goes (the
    app's, liminal_charts.gui.front.serve_front, in mode "fetcher"): `serve`, and the service. Imported
    when asked, not before."""
    from liminal_charts.gui.front import serve_front

    return serve_front
