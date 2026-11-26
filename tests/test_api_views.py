"""The integrator's own two views (1.16.1; Monday list item 17; the user, 2026-11-16: "for all apps, and all plugins,
there should be an external api tab, and an internal api tab"): GET /api/app/apis, answered by its frame (on its page
the data API leaves it to the frame, liminal-charts 0.2.10), served here by the frame's own server on a free port.
Nothing of a plugin is asked, nothing is reached outside this machine."""
from __future__ import annotations

import json
from http.client import HTTPConnection

from liminal_integrator import lib, routes
from liminal_integrator.app import IntegratorApp


def _get(port, path):
    c = HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
    r = c.getresponse()
    raw = r.read()
    return r.status, json.loads(raw)


def _served(app):
    url = app.start(0)
    return int(url.rsplit(":", 1)[1].strip("/"))


def test_the_integrator_answers_its_own_two_views():
    from liminal_charts.gui import routes as charts

    app = IntegratorApp(log=lambda m: None)
    port = _served(app)
    try:
        status, got = _get(port, "/api/app/apis")
    finally:
        app.stop()
    assert status == 200 and got["app"]["app"] == "integrator"
    inner = got["internal"]
    assert inner["name"] == "integrator" and inner["title"] == "Liminal Integrator"
    own = [(r["method"], r["path"]) for r in inner["routes"] if r["own"]]
    assert own[:len(charts.DATA_ROUTES)] == [(r[0], r[1]) for r in charts.DATA_ROUTES]  # the data API's first
    assert own[-len(routes.ROUTES):] == [(r[0], r[1]) for r in routes.ROUTES]  # then its own six
    assert inner["counts"]["own"] == len(own) and inner["counts"]["routes"] > len(own)  # the frame's beside them
    assert [ln["name"] for ln in inner["linked"]] == ["platform"] and "liminal-net" in inner["linked"][0]["how"]
    assert len(inner["notes"]) == len(IntegratorApp.INTERNAL_NOTES)
    assert all(len(n) <= 400 for n in IntegratorApp.INTERNAL_NOTES)


def test_a_charts_from_before_leaves_its_own_six_and_no_error(monkeypatch):
    monkeypatch.setattr(lib, "page_routes", lambda: ((), ()))
    app = IntegratorApp(log=lambda m: None)
    port = _served(app)
    try:
        status, got = _get(port, "/api/app/apis")
    finally:
        app.stop()
    own = [(r["method"], r["path"]) for r in got["internal"]["routes"] if r["own"]]
    assert status == 200 and own == [(r[0], r[1]) for r in routes.ROUTES]
