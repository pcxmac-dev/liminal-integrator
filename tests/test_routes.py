"""The integrator's own routes as its Internal API lists them (routes.py, 1.16.1; Monday list item 17; liminal-libs
1.63.0's internal.py): its six held to IntegratorApp.api, and its routes() as the page's server answers them, the data
API's first (the charts' table), with a charts from before 0.2.10 standing in. Read from the source with ast and the
tables: nothing is started, served or reached."""
from __future__ import annotations

import inspect

from liminal_libs.internal import FRAME_ROUTES, ROUTE_KINDS, ROUTE_METHODS, ROUTE_WHO, literals_in, route_problems

from liminal_integrator import lib, routes
from liminal_integrator.app import IntegratorApp


def _keys(rows) -> list[tuple[str, str]]:
    return [(r[0], r[1]) for r in rows]


def test_its_own_table_is_what_its_api_answers():
    assert route_problems(routes.ROUTES, literals_in(inspect.getsource(IntegratorApp.api))) == []
    assert _keys(routes.ROUTES) == [("GET", "/api/databases"), ("GET", "/api/databases/detail"),
                                    ("GET", "/api/databases/plugins"), ("POST", "/api/databases/instances"),
                                    ("GET", "/api/auditor"), ("POST", "/api/auditor/run")]
    assert IntegratorApp.ROUTES is routes.ROUTES


def test_every_row_is_one_with_its_method_class_and_caller():
    rows = IntegratorApp(log=lambda m: None).routes()
    assert len(set(_keys(rows))) == len(rows)
    for method, path, about, kind, who in rows:
        assert method in ROUTE_METHODS and kind in ROUTE_KINDS and who in ROUTE_WHO, (method, path)
        assert path.startswith("/") and about.strip(), (method, path)
        assert kind in (("read", "stream") if method == "GET" else ("change", "ask", "stream")), (method, path)


def test_the_data_apis_rows_come_first_then_its_own():
    from liminal_charts.gui import routes as charts

    rows = IntegratorApp(log=lambda m: None).routes()
    data = _keys(charts.DATA_ROUTES)
    assert _keys(rows)[:len(data)] == data  # its /api/plugins, /api/interface, /api/ui before the frame's rows
    assert _keys(rows)[-len(routes.ROUTES):] == _keys(routes.ROUTES)
    # the frame's writes its page server does not answer, said so in the integrator's words, never the charts'
    stop = {(m, p): about for m, p, about, *_ in rows if (m, p) in set(charts.NOT_ANSWERED_PATHS)}
    assert set(stop) == {pair for pair in charts.NOT_ANSWERED_PATHS if pair in set(_keys(FRAME_ROUTES))} and stop
    for about in stop.values():
        assert about.startswith(routes.UNANSWERED) and "liminal-stop-integrator" in about and "charts" not in about


def test_a_charts_without_its_table_leaves_its_own_six(monkeypatch):
    monkeypatch.setattr(lib, "page_routes", lambda: ((), ()))
    assert IntegratorApp(log=lambda m: None).routes() == routes.ROUTES


def test_page_routes_says_none_for_a_charts_from_before(monkeypatch):
    import builtins

    real = builtins.__import__

    def without(name, *args, **kwargs):
        if name == "liminal_charts.gui.routes":
            raise ImportError(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without)
    assert lib.page_routes() == ((), ())


def test_unanswered_leaves_out_what_the_frame_has_no_row_of():
    assert routes.unanswered([("POST", "/api/nothing-here")]) == ()
