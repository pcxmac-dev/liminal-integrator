"""The database plugins' instances on the integrator's page (instances.py, app.py's routes; the user, 2026-11-15: "for
the integrator i need plugins for each type of database and in each plugin can setup either new databases or
connections to existing databases ... each instance in the plugin has it's own configuration how it's shared, ports,
permissions etc"). Two stand-in engines, a file's and a server's, found by the registry as packages would be; the
integrator attaches them with its login (a dict here), lists their instances with the folder's own figures, and
carries the page's forms to them: a change only once confirmed, a refusal with what accepts it, never a secret back.
The files are plain text in the test's folder; nothing listens, nothing is opened (conftest refuses the real openers)."""
from __future__ import annotations

import json
from http import HTTPStatus
from types import SimpleNamespace

import pytest

from liminal_integrator import databases as dbs
from liminal_integrator import instances, lib
from liminal_integrator.app import IntegratorApp
from liminal_libs import layout, mounts
from liminal_libs.sources import registry
from liminal_libs.sources.apis import Api, Link as Page
from liminal_libs.storage import databases as contract
from liminal_libs.storage.databases import DatabasePlugin, Instance


def docs(name: str) -> tuple:
    return (Api(name=name, maker="the tests", about="a stand-in engine", kind="file",
                links=(Page("Its documentation", "https://www.sqlite.org/docs.html", "docs"),), verified="2026-11-16"),)


class Flat(DatabasePlugin):
    """A file engine's stand-in: a database is a text file that begins with the word flat."""

    name, title, about, api, order = "sqlite", "Flat", "a file engine's stand-in", "2.3", 940
    options = ("SQLITE_INSTANCES",)
    apis = docs("Flat files")
    ENGINE, METHODS, HOLDS, SHARES = "sqlite", ("file", "helper"), ("main", "bars"), True

    def builtin(self, data_dir):
        return (Instance("data", "The data folder", where="./", holds=self.HOLDS),)

    def open(self, instance, part="", read_only=True, data_dir=None):
        return open(self.path_of(instance, data_dir), encoding="utf-8")

    def probe(self, instance, data_dir):
        if instance.folder:
            return ["a folder of flat files"]
        with self.open(instance, data_dir=data_dir) as f:
            if f.readline().strip() != "flat":
                raise ValueError("not a flat file")
        return ["flat 1"]

    def make(self, instance, data_dir, **given):
        path = self.path_of(instance, data_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("flat\n", encoding="utf-8", newline="\n")
        return [f"{path.name} made"]

    def api_facts(self):
        return {"Flat files": {"Version": "1"}}


class Served(DatabasePlugin):
    """A server engine's stand-in: `servers` is what answers, by (host, port): each database with its roles."""

    name, title, about, api, order = "mongodb", "Served", "a server engine's stand-in", "2.3", 941
    options = ("MONGODB_INSTANCES",)
    apis = docs("Served")
    ENGINE, METHODS, HOLDS, SERVER = "mongodb", ("tcp",), ("documents",), True
    SHARED = "its server's roles decide who reaches it"
    servers: dict = {}

    def builtin(self, data_dir):
        return (Instance("local", "The server here", where="127.0.0.1", method="tcp", port=27017, database="liminal",
                         holds=self.HOLDS),)

    def open(self, instance, part="", read_only=True, data_dir=None):
        roles = self.servers.get((instance.where, instance.port), {}).get(instance.database)
        if roles is None:
            raise ConnectionError(f"nothing answers at {instance.where}:{instance.port}/{instance.database}")
        if instance.auth:
            user, password = self.credentials(instance) or ("", "")
            if roles.get(user) != password:
                raise PermissionError(f"the server refused {user}:{password}")  # (a server that repeats what it was sent)
        return roles

    def probe(self, instance, data_dir):
        self.open(instance, data_dir=data_dir)
        return ["served 9.9"]

    def make(self, instance, data_dir, admin_user="", admin_password="", **given):
        if admin_user and admin_password != "admin-secret":
            raise PermissionError(f"the server refused the administrator {admin_user}:{admin_password}")
        self.servers.setdefault((instance.where, instance.port), {})[instance.database] = {}
        return [f"{instance.database} made"]


@pytest.fixture
def integrator(tmp_path, monkeypatch):
    """An integrator on the test's data folder, holding the two stand-ins as the registry found them; its login keeps
    to a dict; nothing listens on this machine, and another machine is never asked whether it does."""
    monkeypatch.setattr(layout, "plugins_dir", lambda: None)
    servers = {("127.0.0.1", 27020): {"research": {}}, ("db.example.net", 27017): {"docs": {"reader": "far-secret"}}}
    monkeypatch.setattr(Served, "servers", servers)
    eps = [SimpleNamespace(name=f"p{i}", value=f"fake_{i}:DATABASE", load=(lambda p=p: SimpleNamespace(DATABASE=p)))
           for i, p in enumerate((Flat(), Served()))]
    monkeypatch.setattr(registry, "_entry_points", lambda: eps)
    registry.reload()

    def listening(host, port, timeout=0.3):
        assert contract.is_local(host), f"{host} asked whether it listens"
        return (host, port) in servers

    monkeypatch.setattr(contract, "listening", listening)
    data = tmp_path / "data"
    for name, text in (("liminal.db", "flat\n"), ("feeds/massive.db", "flat\nbars\n"), ("feeds/massive.db-wal", "log"),
                       ("history/massive/2026-09.1.duckdb", "month")):
        (data / name).parent.mkdir(parents=True, exist_ok=True)
        (data / name).write_text(text, encoding="utf-8", newline="\n")
    env: dict = {}
    said: list = []
    app = IntegratorApp(log=said.append, login=lib.EnvironmentLogin(env=env), db_path=data / "liminal.db")
    yield app, data, env, said
    registry._providers = None


def get(app, path, **query):
    status, body = app.api(None, "GET", path, query, None)[:2]
    assert status == 200
    return body


def post(app, **form):
    status, body = app.api(None, "POST", "/api/databases/instances", {}, form)[:2]
    assert status == 200
    return body


def test_the_page_is_given_every_engines_plugin_with_its_instances(integrator):
    app, data, env, said = integrator
    page = get(app, "/api/databases/plugins")
    assert [p["name"] for p in page["plugins"]] == ["sqlite", "mongodb"] and page["dataFolder"] == str(data) and page["errors"] == []
    assert "::" in page["me"] and page["suites"][0] == page["me"]
    files, server = page["plugins"]
    assert (files["engine"], files["engineTitle"], files["server"], files["shares"]) == ("sqlite", "SQLite", False, True)
    assert files["can"] == {"new": True, "connect": True, "share": True, "forget": True, "why": ""}
    assert files["apis"][0]["name"] == "Flat files" and files["apis"][0]["docs"].startswith("https://")  # its API card
    assert files["apiFacts"] == {"Flat files": {"Version": "1"}}
    (own,) = files["instances"]
    assert (own["name"], own["builtin"], own["state"], own["method"], own["place"]) == ("data", True, "ready", "file", str(data))
    assert (own["files"], own["bytes"]) == (2, len("flat\n") + len("flat\nbars\n") + len("log"))  # the folder's own figures
    (here,) = server["instances"]
    assert (here["name"], here["state"], here["address"]) == ("local", "not running", "127.0.0.1:27017/liminal")
    assert here["running"] is False and server["sharedNote"] == "its server's roles decide who reaches it"
    # attached by the integrator with its login at the first ask: what is added is kept through it
    assert all(p.app is app for p in registry.databases().values()) and sorted(instances.plugins(app)) == ["mongodb", "sqlite"]
    assert any("sqlite attached (database" in line for line in said) and env == {}
    json.dumps(page)  # what a page is given is plain data


def test_a_form_is_answered_by_its_plugin_and_a_change_only_once_the_page_confirmed_it(integrator):
    app, data, env, said = integrator
    with pytest.raises(lib.Refused, match="confirmed on the page first") as e:
        post(app, plugin="sqlite", action="new", name="archive")
    assert e.value.status == HTTPStatus.BAD_REQUEST and not (data / "instances").exists() and env == {}
    made = post(app, plugin="sqlite", action="new", name="archive", holds=["bars"], title="Old bars", confirm=True)
    assert made["ok"] and made["said"] == f"archive made: {data / 'instances' / 'archive.db'}" and (data / "instances" / "archive.db").is_file()
    assert json.loads(env["SQLITE_INSTANCES"])["instances"][0]["holds"] == ["bars"]
    assert said[-1] == f"integrator: sqlite: new archive: archive made: {data / 'instances' / 'archive.db'}"
    # listed at once with the folder's own, in the group of the instances; a test needs no confirmation
    entry = next(x for x in get(app, "/api/databases")["entries"] if x["id"] == "instances/archive.db")
    assert (entry["group"], entry["engine"], entry["size"]) == ("instances", "sqlite", 5)
    assert post(app, plugin="sqlite", action="test", name="archive")["lines"] == ["flat 1"]
    assert post(app, plugin="sqlite", action="share", name="data", who="linux::Ubuntu", access="read", confirm=True)["said"] == (
        "linux::Ubuntu reads data")
    rows = {r["name"]: r for r in get(app, "/api/databases/plugins")["plugins"][0]["instances"]}
    assert rows["data"]["sharedWords"] == "linux::Ubuntu reads only; no other suite attaches" and rows["archive"]["made"] is True
    assert rows["archive"]["bytes"] == 5 and "files" not in rows["archive"]
    assert post(app, plugin="sqlite", action="forget", name="archive", confirm=True)["said"] == "archive forgotten"
    assert (data / "instances" / "archive.db").is_file()  # what it holds stays
    # what is not text is as not given: no form's oddity reaches a plugin
    odd = post(app, plugin="sqlite", action="new", name="odd", holds={"odd": 1}, where=["odd"], title=7, confirm=True)
    assert odd["said"] == f"odd made: {data / 'instances' / 'odd.db'}"
    for form, status, why in (
            ({"plugin": "oracle", "action": "test", "name": "x"}, HTTPStatus.NOT_FOUND, "no database plugin 'oracle' here"),
            ({"plugin": "sqlite", "action": "drop", "name": "x"}, HTTPStatus.BAD_REQUEST, "an instance is asked one of"),
            ({"plugin": "sqlite", "action": "test", "name": "nope"}, HTTPStatus.NOT_FOUND, "Flat has no instance 'nope'"),
            ({"plugin": "sqlite", "action": "forget", "name": "data", "confirm": True}, HTTPStatus.BAD_REQUEST, "is Flat's own"),
            ({"plugin": "sqlite", "action": "port", "name": "data", "port": 1, "confirm": True}, HTTPStatus.BAD_REQUEST, "it has no port")):
        with pytest.raises(lib.Refused, match=why) as e:
            post(app, **form)
        assert e.value.status == status, form


def test_an_instance_outside_the_data_folder_is_listed_with_the_folders_own_and_looked_into(integrator, tmp_path, monkeypatch):
    app, data, env, said = integrator
    old = tmp_path / "disk2" / "old.db"
    old.parent.mkdir()
    old.write_text("flat\nrows\n", encoding="utf-8", newline="\n")
    old.with_name("old.db-wal").write_text("log!", encoding="utf-8")
    assert post(app, plugin="sqlite", action="connect", name="old", where=str(old), title="The old one", confirm=True)["ok"]
    assert instances.elsewhere(app) == [{"id": "instance:sqlite:old", "plugin": "sqlite", "name": "old", "title": "The old one",
                                         "engine": "sqlite", "path": str(old)}]
    listing = get(app, "/api/databases")
    entry = next(x for x in listing["entries"] if x["id"] == "instance:sqlite:old")
    assert (entry["name"], entry["group"], entry["kind"], entry["path"]) == ("The old one", "instances", "file", str(old))
    assert (entry["size"], entry["file"], entry["side"]) == (14, 10, {"wal": 4})
    assert {"id": "instances", "title": "Instances"}.items() <= next(g for g in listing["groups"] if g["id"] == "instances").items()
    # looked into like any file of the folder: opened by the view's own reader, for reading
    opened: list = []

    def reader(path):
        opened.append(path)
        raise RuntimeError("a stand-in: nothing is opened")

    monkeypatch.setattr(dbs, "connect_sqlite", reader)
    detail = get(app, "/api/databases/detail", id="instance:sqlite:old")
    assert opened == [old] and detail["figures"]["error"] == "RuntimeError: a stand-in: nothing is opened"
    # gone since: left out of the list, said by its plugin
    old.unlink()
    app.databases.forget()
    assert all(x["id"] != "instance:sqlite:old" for x in get(app, "/api/databases")["entries"])
    assert get(app, "/api/databases/plugins")["plugins"][0]["instances"][1]["state"] == "absent"
    # a plugin whose instances cannot be read does not take the folder's list with it
    monkeypatch.setattr(Flat, "instances", lambda self, data_dir=None: 1 / 0)
    app.databases.forget()
    assert instances.elsewhere(app) == [] and get(app, "/api/databases")["totals"]["databases"] >= 3
    assert "ZeroDivisionError" in get(app, "/api/databases/plugins")["plugins"][0]["error"]


def test_a_refusal_names_what_accepts_it_and_a_secret_never_comes_back(integrator):
    app, data, env, said = integrator
    far = {"plugin": "mongodb", "action": "connect", "name": "far", "where": "db.example.net", "database": "docs", "tls": True,
           "user": "reader", "password": "far-secret", "confirm": True}
    with pytest.raises(instances.Asked, match="db.example.net is not this machine") as first:
        post(app, **far)
    assert first.value.status == HTTPStatus.BAD_REQUEST and first.value.accept == "accept_remote"
    assert first.value.answer() == {"error": first.value.reason, "accept": "accept_remote"} and env == {}
    with pytest.raises(instances.Asked) as wrong:  # the engine's own failure, which repeats what it was sent
        post(app, **{**far, "accept_remote": True, "password": "wr0ng-pass"})
    assert wrong.value.accept is None and "wr0ng-pass" not in wrong.value.reason and "(not shown)" in wrong.value.reason
    assert wrong.value.answer() == {"error": wrong.value.reason} and env == {}
    kept = post(app, **{**far, "accept_remote": True})
    assert kept["said"] == "far connected: db.example.net:27017/docs"
    everything = json.dumps(kept) + json.dumps(get(app, "/api/databases/plugins")) + "".join(said) + env["MONGODB_INSTANCES"]
    assert "far-secret" not in everything and env["MONGODB_FAR_PASSWORD"] == "far-secret"
    row = get(app, "/api/databases/plugins")["plugins"][1]["instances"][1]
    assert (row["name"], row["remote"], row["tls"], row["signsIn"], row["state"]) == ("far", True, True, True, "not asked")
    # the administrator of a new database is asked once and not kept, nor repeated when the server refuses
    with pytest.raises(instances.Asked) as refused:
        post(app, plugin="mongodb", action="new", name="filings", where="127.0.0.1", port=27020, admin_user="root",
             admin_password="n0t-the-one", confirm=True)
    assert refused.value.status == HTTPStatus.BAD_GATEWAY and "n0t-the-one" not in refused.value.reason
    made = post(app, plugin="mongodb", action="new", name="filings", where="127.0.0.1", port="27020", admin_user="root",
                admin_password="admin-secret", confirm=True)
    assert made["said"] == "filings made: 127.0.0.1:27020/filings" and "admin-secret" not in json.dumps(made) + json.dumps(env) + "".join(said)
    assert post(app, plugin="mongodb", action="port", name="filings", port=27020, confirm=True)["said"] == "filings's port is 27020 already"
    assert post(app, plugin="mongodb", action="credentials", name="far", user="reader", password="far-secret", confirm=True)["ok"]
    with pytest.raises(instances.Asked, match="its server's roles decide who reaches it"):
        post(app, plugin="mongodb", action="share", name="local", who="linux::Ubuntu", access="read", confirm=True)


def test_from_another_system_the_instances_are_read_and_nothing_of_them_is_changed(integrator, monkeypatch):
    app, data, env, said = integrator
    post(app, plugin="sqlite", action="new", name="archive", confirm=True)
    theirs = env["SQLITE_INSTANCES"]
    monkeypatch.setattr(mounts, "foreign", lambda path, mounts=None: True)
    monkeypatch.setattr("liminal_libs.config.UserEnvironment.saved", lambda self: {"SQLITE_INSTANCES": theirs})
    files = get(app, "/api/databases/plugins")["plugins"][0]
    assert [r["name"] for r in files["instances"]] == ["data", "archive"] and files["can"]["new"] is False
    assert "changed from that system" in files["can"]["why"] and [r["method"] for r in files["instances"]] == ["helper", "helper"]
    with pytest.raises(instances.Asked, match="done from that system, not from here") as e:
        post(app, plugin="sqlite", action="share", name="data", who="linux::Ubuntu", access="write", confirm=True)
    assert e.value.status == HTTPStatus.CONFLICT and env["SQLITE_INSTANCES"] == theirs
    assert post(app, plugin="sqlite", action="test", name="archive")["ok"]  # asking is still fine


def test_a_database_plugin_left_out_at_loading_is_said_on_the_page(integrator, monkeypatch):
    app, data, env, said = integrator
    monkeypatch.setattr(lib, "plugin_errors", lambda: [
        ("plugin-integrator-duckdb (plugin_integrator_duckdb)", "ModuleNotFoundError: No module named 'duckdb'"),
        ("package: fake", "database 'sqlite-too': 'sqlite' is the plugin for sqlite already"),
        ("plugin-integrator-twse (plugin_integrator_twse)", "ImportError: something of a feed's")])
    assert get(app, "/api/databases/plugins")["errors"] == [
        "plugin-integrator-duckdb (plugin_integrator_duckdb): ModuleNotFoundError: No module named 'duckdb'",
        "package: fake: database 'sqlite-too': 'sqlite' is the plugin for sqlite already"]
