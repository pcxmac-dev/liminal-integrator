"""The integrator's code base (1.13.4; Monday list item 15: "Codebase in the login's, the integrator's and the charts'
pages (the platform has it)"): the library's object every App holds (liminal_libs.apps.Codebase), the integrator's
answered by its frame at GET /api/codebase and POST /api/codebase/fetch, and drawn on its page by the charts' code
(liminal-charts 0.2.4: the Codebase view, the integrator's page passing the fetch to this frame). Served here by the
frame's own server on a free port; the code base is given a workspace of the test's own and a stand-in runner: no git
runs, no repository of this machine is read."""
from __future__ import annotations

import json
import time
from http.client import HTTPConnection
from pathlib import Path

from liminal_libs.apps import Codebase

import liminal_integrator
from liminal_integrator.app import IntegratorApp


def _call(port, method, path, body=None, header=True):
    c = HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Host": f"127.0.0.1:{port}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if header and method != "GET":
        headers["X-Liminal-Charts"] = "1"
    c.request(method, path, body=None if body is None else json.dumps(body), headers=headers)
    r = c.getresponse()
    raw = r.read()
    try:
        return r.status, json.loads(raw)
    except ValueError:
        return r.status, raw


def test_the_integrator_answers_its_code_base(tmp_path):
    app = IntegratorApp(log=lambda m: None)
    # what it runs from, as the code base finds it by itself: the integrator's own code and the library (nothing read)
    parts = dict(app.codebase.parts())
    assert parts["the integrator app"] == Path(liminal_integrator.__file__).resolve().parent and "the library" in parts
    ws = tmp_path / "ws"
    (ws / "store" / ".git").mkdir(parents=True)
    (ws / "store" / "fetcher.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    asked: list[str] = []

    def runner(args, cwd, timeout):
        said = " ".join(args)
        asked.append(said)
        if said.startswith("git status"):
            return 0, b"# branch.head main\n# branch.upstream origin/main\n# branch.ab +0 -4\n", b""
        if said.startswith("git config --get-regexp"):
            return 0, b"remote.origin.url https://example.test/store.git\n", b""
        if said.startswith("git config --get"):
            return 0, b"https://someone:tok3n@example.test/store.git\n", b""
        if said.startswith("git ls-files"):
            return 0, b"fetcher.py\0", b""
        if said.startswith(("git log", "git fetch")):
            return 0, b"", b""
        return 127, b"", b"not installed here"

    app.codebase = Codebase(app, roots=[ws], runner=runner, own_parts=lambda: [("the integrator app", ws / "store")])
    url = app.start(0)
    port = int(url.rsplit(":", 1)[1].strip("/"))
    try:
        assert _call(port, "GET", "/api/codebase")[0] == 200
        app.codebase.wait()
        status, got = _call(port, "GET", "/api/codebase")
        assert status == 200 and got["state"] == "ready" and got["app"] == "integrator" and got["totals"]["repositories"] == 1
        repo = got["repositories"][0]
        assert (repo["name"], repo["branch"], repo["behind"], repo["used"]) == ("store", "main", 4, ["the integrator app"])
        assert repo["remote"] == "https://example.test/store.git" and "tok3n" not in json.dumps(got)
        assert [(lang["name"], lang["lines"]) for lang in got["languages"]] == [("Python", 2)]
        assert not [a for a in asked if a.startswith("git fetch")]  # a reading asks no remote
        assert _call(port, "POST", "/api/codebase/fetch", {}, header=False)[0] == 403  # a write: the page's own alone
        assert _call(port, "POST", "/api/codebase/fetch", {}) == (202, {"started": True})
        end = time.monotonic() + 10
        while not (app.codebase.snapshot().get("fetching") or {}).get("ended") and time.monotonic() < end:
            time.sleep(0.02)
        assert "git fetch --quiet" in asked
    finally:
        app.stop()
