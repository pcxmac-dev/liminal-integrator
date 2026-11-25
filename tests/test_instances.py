"""The database plugins' instances on the integrator's page (instances.py, app.py's routes; the user, 2026-11-15: "for
the integrator i need plugins for each type of database and in each plugin can setup either new databases or
connections to existing databases ... each instance in the plugin has it's own configuration how it's shared, ports,
permissions etc"). Two stand-in engines, a file's and a server's, found by the registry as packages would be; the
integrator attaches them with its login (a dict here), lists their instances with the folder's own figures, and
carries the page's forms: a change only once confirmed, a refusal with what accepts it, never a secret back.

1.15.0 (Monday list item 30, step 4; the user, 2026-11-24: "inheritance bro", "through the rust interface"; 2026-11-25:
the platform the only writer of instance settings): the integrator inherits the library's platform core and is not
its writer. A test is answered here; a change is asked of the running platform through its liminal-net node and made
there, through the same user's environment (the dict both logins keep to), and its refusal comes back as it was said
there. The running platform is a writer of the library's platform core holding its own copies of the stand-ins (its
own process's registry), and liminal-net is stood in for: nothing listens, nothing is started, nothing is sent.
The files are plain text in the test's folder; nothing listens, nothing is opened (conftest refuses the real openers)."""
from __future__ import annotations

import json
from http import HTTPStatus
from types import SimpleNamespace

import pytest

from liminal_integrator import databases as dbs
from liminal_integrator import instances, lib
from liminal_integrator.app import PLATFORM_DOWN, IntegratorApp
from liminal_libs import layout, mounts
from liminal_libs.apps import databases as section
from liminal_libs.apps import platform as core
from liminal_libs.apps.platform import Platform
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




# -- liminal-net, stood in -----------------------------------------------------------------------------------------------
class RemoteError(Exception):
    """liminal_net.RemoteError as it comes back: the kind, the words, status and accept."""

    def __init__(self, kind, message, status=None, accept=None):
        super().__init__(f"{kind}: {message}")
        self.kind, self.message, self.status, self.accept = kind, message, status, accept


class StandInRemote:
    """A synapse to a node served by another process: each request given to its hillock as liminal-net gives it (the
    peer as a dict, the args as a list), in that process (its registry: the platform's own copies of the plugins), an
    exception back as a record (kind, words, status, accept)."""

    def __init__(self, hillock, peer, plugins):
        self.hillock, self.peer, self.plugins = hillock, peer, plugins
        self.interface = hillock.interface
        self.asked: list = []

    def request(self, method, *args, **kwargs):
        self.asked.append((method, json.loads(json.dumps(list(args)))))  # what crosses is plain data
        if method not in self.interface["methods"]:
            raise RemoteError("Refused", f"no method {method}", 404)
        ours = registry.databases
        registry.databases = lambda: dict(self.plugins)  # the platform's process finds its own plugins
        try:
            return self.hillock.request(self.peer, method, list(args), dict(kwargs))
        except Exception as e:  # noqa: BLE001 - what crosses: a record
            raise RemoteError(type(e).__name__, getattr(e, "reason", str(e)), getattr(e, "status", None),
                              getattr(e, "accept", None)) from None
        finally:
            registry.databases = ours


class StandInNode:
    """liminal_net.Node stood in for: `served` the nodes this test's network holds (name -> (hillock, its plugins))."""

    served: dict = {}
    made: list = []

    def __init__(self, name, kind, scope, hillock, interface, ipc_dir=None, timing=None):
        self.name, self.kind, self.scope, self.hillock, self.interface = name, kind, scope, hillock, interface
        self.started, self.stopped, self.reached, self.remotes = False, [], [], []
        StandInNode.made.append(self)

    def start(self):
        self.started = True

    def stop(self, why):
        self.stopped.append(why)

    def reach(self, node, scope=None, launcher=None):
        self.reached.append((node, launcher))
        if node not in StandInNode.served:
            raise ConnectionError(f"no node {node} answers")  # liminal_net.NetworkError is a ConnectionError
        hillock, plugins = StandInNode.served[node]
        remote = StandInRemote(hillock, {"name": self.name, "kind": self.kind, "scope": self.scope, "pid": 4242}, plugins)
        self.remotes.append(remote)
        return remote


class Running(Platform):
    """The running platform (liminal-platform's PlatformApp, its Databases section alone): the one writer."""

    NAME, TITLE, ICON = "platform", "The platform", "chip"
    PLATFORM_NEEDS = ("database",)
    PLATFORM_WRITER = True


@pytest.fixture
def integrator(tmp_path, monkeypatch):
    """An integrator on the test's data folder, holding the two stand-ins as the registry found them; its login keeps
    to a dict; nothing listens on this machine, and another machine is never asked whether it does. Its node reaches
    only this test's stand-in network (none served: no platform runs)."""
    monkeypatch.setattr(layout, "plugins_dir", lambda: None)
    monkeypatch.setattr(StandInNode, "served", {})
    monkeypatch.setattr(StandInNode, "made", [])
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
    app = IntegratorApp(log=said.append, login=lib.EnvironmentLogin(env=env), db_path=data / "liminal.db",
                        node_factory=StandInNode)
    app.PLATFORM_SCOPE = tmp_path
    yield app, data, env, said
    registry._providers = None


@pytest.fixture
def platform(integrator, tmp_path):
    """The running platform, served as its node on the stand-in network: its own copies of the two plugins (another
    process's), the same user's environment for its login (the integrator's dict), the same data folder."""
    app, data, env, said = integrator
    theirs: list = []
    running = Running(log=theirs.append, login=lib.EnvironmentLogin(env=env), node_factory=StandInNode)
    running.db_path = data / "liminal.db"
    node = running.serve_databases(scope=tmp_path)
    StandInNode.served[node.name] = (node.hillock, {"sqlite": Flat(), "mongodb": Served()})
    return SimpleNamespace(app=running, node=node, said=theirs)


def get(app, path, **query):
    status, body = app.api(None, "GET", path, query, None)[:2]
    assert status == 200
    return body


def answer(app, **form):
    """A form's answer as the frame's handler sends it: (status, body), a Refused as {"error"}."""
    try:
        return app.api(None, "POST", "/api/databases/instances", {}, form)[:2]
    except lib.Refused as e:
        return e.status, {"error": e.reason}


def post(app, **form):
    status, body = answer(app, **form)
    assert status == 200, body
    return body


def test_the_integrator_inherits_the_platform_core_and_is_not_its_writer(integrator):
    app, data, env, said = integrator
    assert issubclass(IntegratorApp, Platform) and IntegratorApp.PLATFORM_NEEDS == ("database",)
    assert IntegratorApp.PLATFORM_WRITER is False and not app.is_platform and app.needs("database")
    for _ in range(2):  # (no feed in this registry) the database plugins, each named once
        assert app.attach_plugins() == ["sqlite", "mongodb"]
    assert sorted(app.section("databases")) == ["mongodb", "sqlite"] and all(p.app is app for p in registry.databases().values())
    with pytest.raises(RuntimeError, match="not the running platform"):
        app.serve_databases(node_factory=StandInNode)  # it serves no Databases section
    assert StandInNode.made == []  # and makes no node until a change is asked
    # instances.py is the library's names, not copies of them
    assert instances.Asked is section.Asked and instances.ask is section.ask and instances.ours is section.ours
    assert instances.overview is section.overview and instances.elsewhere is section.elsewhere


def test_the_page_is_given_every_engines_plugin_with_its_instances(integrator):
    app, data, env, said = integrator
    page = get(app, "/api/databases/plugins")
    assert [p["name"] for p in page["plugins"]] == ["sqlite", "mongodb"] and page["dataFolder"] == str(data) and page["errors"] == []
    assert "::" in page["me"] and page["suites"][0] == page["me"] and page["writer"] is False
    files, server = page["plugins"]
    assert (files["engine"], files["engineTitle"], files["server"], files["shares"]) == ("sqlite", "SQLite", False, True)
    # no change offered here: each plugin says where one is made (the platform, the one writer)
    assert files["can"] == {"new": False, "connect": False, "share": False, "forget": False, "why": core.ELSEWHERE}
    assert files["apis"][0]["name"] == "Flat files" and files["apis"][0]["docs"].startswith("https://")  # its API card
    assert files["apiFacts"] == {"Flat files": {"Version": "1"}}
    (own,) = files["instances"]
    assert (own["name"], own["builtin"], own["state"], own["method"], own["place"]) == ("data", True, "ready", "file", str(data))
    assert (own["files"], own["bytes"]) == (2, len("flat\n") + len("flat\nbars\n") + len("log"))  # the folder's own figures
    (here,) = server["instances"]
    assert (here["name"], here["state"], here["address"]) == ("local", "not running", "127.0.0.1:27017/liminal")
    assert here["running"] is False and server["sharedNote"] == "its server's roles decide who reaches it"
    # attached by the integrator with its login at the first ask: what it reads is read through it
    assert all(p.app is app for p in registry.databases().values()) and sorted(instances.plugins(app)) == ["mongodb", "sqlite"]
    assert any("sqlite attached (database" in line for line in said) and env == {}
    json.dumps(page)  # what a page is given is plain data


def test_a_change_is_made_on_the_platform_through_its_node_and_only_once_the_page_confirmed_it(integrator, platform):
    app, data, env, said = integrator
    status, body = answer(app, plugin="sqlite", action="new", name="archive")
    assert status == HTTPStatus.BAD_REQUEST and "confirmed on the page first" in body["error"]  # the platform's words
    assert not (data / "instances").exists() and env == {}
    made = post(app, plugin="sqlite", action="new", name="archive", holds=["bars"], title="Old bars", confirm=True)
    assert made["ok"] and made["said"] == f"archive made: {data / 'instances' / 'archive.db'}" and (data / "instances" / "archive.db").is_file()
    assert json.loads(env["SQLITE_INSTANCES"])["instances"][0]["holds"] == ["bars"]  # kept through the login alone
    # made there, by the platform, asked by the integrator's node (reached without a launcher: never started)
    assert platform.said[-2:] == ["platform: sqlite: new archive: " + made["said"],
                                  "platform: asked by app-integrator-platform through its node: sqlite new"]
    (own,) = [n for n in StandInNode.made if n.name == "app-integrator-platform"]
    assert not own.started and {r for r in own.reached} == {(core.DATABASES_NODE, None)}
    assert [m for r in own.remotes for m, _ in r.asked] == ["change", "change"]
    assert not any(": new archive:" in line for line in said)  # nothing of it made here
    # listed here at once with the folder's own, in the group of the instances; a test is answered here, unconfirmed
    entry = next(x for x in get(app, "/api/databases")["entries"] if x["id"] == "instances/archive.db")
    assert (entry["group"], entry["engine"], entry["size"]) == ("instances", "sqlite", 5)
    assert post(app, plugin="sqlite", action="test", name="archive")["lines"] == ["flat 1"]
    assert [m for r in own.remotes for m, _ in r.asked] == ["change", "change"]  # (the test asked nothing there)
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
    for form, want, why in (
            ({"plugin": "oracle", "action": "test", "name": "x"}, HTTPStatus.NOT_FOUND, "no database plugin 'oracle' here"),
            ({"plugin": "sqlite", "action": "drop", "name": "x"}, HTTPStatus.BAD_REQUEST, "an instance is asked one of"),
            ({"plugin": "sqlite", "action": "test", "name": "nope"}, HTTPStatus.NOT_FOUND, "Flat has no instance 'nope'"),
            ({"plugin": "oracle", "action": "new", "name": "x", "confirm": True}, HTTPStatus.NOT_FOUND, "no database plugin 'oracle'"),
            ({"plugin": "sqlite", "action": "forget", "name": "data", "confirm": True}, HTTPStatus.BAD_REQUEST, "is Flat's own"),
            ({"plugin": "sqlite", "action": "port", "name": "data", "port": 1, "confirm": True}, HTTPStatus.BAD_REQUEST, "it has no port")):
        status, body = answer(app, **form)
        assert status == want and why in body["error"], (form, status, body)


def test_with_no_platform_running_a_change_is_said_in_words_and_nothing_is_started_or_written(integrator):
    app, data, env, said = integrator
    status, body = answer(app, plugin="sqlite", action="new", name="archive", confirm=True)
    assert (status, body) == (HTTPStatus.SERVICE_UNAVAILABLE, {"error": PLATFORM_DOWN})
    assert PLATFORM_DOWN == "change this on the platform's Databases section; the platform is not running"
    assert env == {} and not (data / "instances").exists()
    (own,) = StandInNode.made
    assert not own.started and own.reached == [(core.DATABASES_NODE, None)]  # reached without a launcher: never started
    assert said[-1].startswith("integrator: sqlite new not asked: the platform is not running")
    # what needs no writer is answered all the same: the list, a test, the folder's figures
    assert get(app, "/api/databases/plugins")["plugins"][0]["name"] == "sqlite"
    assert post(app, plugin="sqlite", action="test", name="data")["ok"]
    assert get(app, "/api/databases")["entries"]


def test_an_instance_outside_the_data_folder_is_listed_with_the_folders_own_and_looked_into(integrator, platform, tmp_path, monkeypatch):
    app, data, env, said = integrator
    old = tmp_path / "disk2" / "old.db"
    old.parent.mkdir()
    old.write_text("flat\nrows\n", encoding="utf-8", newline="\n")
    old.with_name("old.db-wal").write_text("log!", encoding="utf-8")
    assert get(app, "/api/databases")["entries"]  # (the folder listed before the change: listed again after it)
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


def test_a_refusal_names_what_accepts_it_and_a_secret_never_comes_back(integrator, platform):
    app, data, env, said = integrator
    far = {"plugin": "mongodb", "action": "connect", "name": "far", "where": "db.example.net", "database": "docs", "tls": True,
           "user": "reader", "password": "far-secret", "confirm": True}
    # the route answers what accepts the refusal (the frame's own handler of a Refused would send only its words)
    status, first = answer(app, **far)
    assert status == HTTPStatus.BAD_REQUEST and first["accept"] == "accept_remote"
    assert "db.example.net is not this machine" in first["error"] and set(first) == {"error", "accept"} and env == {}
    status, wrong = answer(app, **{**far, "accept_remote": True, "password": "wr0ng-pass"})  # the engine's own failure,
    assert status == HTTPStatus.BAD_REQUEST and set(wrong) == {"error"}                      # which repeats what it was sent
    assert "wr0ng-pass" not in wrong["error"] and "(not shown)" in wrong["error"] and env == {}
    kept = post(app, **{**far, "accept_remote": True})
    assert kept["said"] == "far connected: db.example.net:27017/docs"
    everything = (json.dumps(kept) + json.dumps(get(app, "/api/databases/plugins")) + "".join(said) + "".join(platform.said)
                  + env["MONGODB_INSTANCES"])
    assert "far-secret" not in everything and env["MONGODB_FAR_PASSWORD"] == "far-secret"
    row = get(app, "/api/databases/plugins")["plugins"][1]["instances"][1]
    assert (row["name"], row["remote"], row["tls"], row["signsIn"], row["state"]) == ("far", True, True, True, "not asked")
    # the administrator of a new database is asked once and not kept, nor repeated when the server refuses
    status, refused = answer(app, plugin="mongodb", action="new", name="filings", where="127.0.0.1", port=27020,
                             admin_user="root", admin_password="n0t-the-one", confirm=True)
    assert status == HTTPStatus.BAD_GATEWAY and "n0t-the-one" not in refused["error"]
    made = post(app, plugin="mongodb", action="new", name="filings", where="127.0.0.1", port="27020", admin_user="root",
                admin_password="admin-secret", confirm=True)
    assert made["said"] == "filings made: 127.0.0.1:27020/filings"
    assert "admin-secret" not in json.dumps(made) + json.dumps(env) + "".join(said) + "".join(platform.said)
    assert post(app, plugin="mongodb", action="port", name="filings", port=27020, confirm=True)["said"] == "filings's port is 27020 already"
    assert post(app, plugin="mongodb", action="credentials", name="far", user="reader", password="far-secret", confirm=True)["ok"]
    status, body = answer(app, plugin="mongodb", action="share", name="local", who="linux::Ubuntu", access="read", confirm=True)
    assert status == HTTPStatus.BAD_REQUEST and "its server's roles decide who reaches it" in body["error"]


def test_from_another_system_the_instances_are_read_and_nothing_of_them_is_changed(integrator, platform, monkeypatch):
    app, data, env, said = integrator
    post(app, plugin="sqlite", action="new", name="archive", confirm=True)
    theirs = env["SQLITE_INSTANCES"]
    monkeypatch.setattr(mounts, "foreign", lambda path, mounts=None: True)
    monkeypatch.setattr("liminal_libs.config.UserEnvironment.saved", lambda self: {"SQLITE_INSTANCES": theirs})
    files = get(app, "/api/databases/plugins")["plugins"][0]
    assert [r["name"] for r in files["instances"]] == ["data", "archive"] and files["can"]["new"] is False
    assert [r["method"] for r in files["instances"]] == ["helper", "helper"]
    status, body = answer(app, plugin="sqlite", action="share", name="data", who="linux::Ubuntu", access="write", confirm=True)
    assert status == HTTPStatus.CONFLICT and "done from that system, not from here" in body["error"]  # the platform's words
    assert env["SQLITE_INSTANCES"] == theirs
    assert post(app, plugin="sqlite", action="test", name="archive")["ok"]  # asking is still fine


def test_a_database_plugin_left_out_at_loading_is_said_on_the_page(integrator, monkeypatch):
    app, data, env, said = integrator
    # (by its package's name as it is since the rename, plugin-platform-*, or as it was, plugin-integrator-*)
    monkeypatch.setattr(registry, "errors", lambda: [
        ("plugin-platform-duckdb (plugin_platform_duckdb)", "ModuleNotFoundError: No module named 'duckdb'"),
        ("plugin-integrator-mongodb (plugin_integrator_mongodb)", "ModuleNotFoundError: No module named 'pymongo'"),
        ("package: fake", "database 'sqlite-too': 'sqlite' is the plugin for sqlite already"),
        ("plugin-integrator-twse (plugin_integrator_twse)", "ImportError: something of a feed's")])
    assert get(app, "/api/databases/plugins")["errors"] == [
        "plugin-platform-duckdb (plugin_platform_duckdb): ModuleNotFoundError: No module named 'duckdb'",
        "plugin-integrator-mongodb (plugin_integrator_mongodb): ModuleNotFoundError: No module named 'pymongo'",
        "package: fake: database 'sqlite-too': 'sqlite' is the plugin for sqlite already"]
