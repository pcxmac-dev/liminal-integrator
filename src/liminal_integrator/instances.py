"""The database plugins' instances on the integrator's page (its Databases view; liminal-integrator 1.12.0).

The user, 2026-11-15: "for the integrator i need plugins for each type of database and in each plugin can setup either
new databases or connections to existing databases using many different types of IP or IPC methods. each instance in
the plugin has it's own configuration how it's shared, ports, permissions etc". The plugins are the library's kind
(liminal_libs.storage.databases: DatabasePlugin, plugin API 2.3): SQLite's, DuckDB's, MongoDB's, each a package of its
own. The integrator is the app that holds them: it attaches them with its login (what you add is kept through it),
lists each one's instances for the page, and carries the page's forms to them.

- `overview(app)`: every database plugin with its instances as the page draws them (`GET /api/databases/plugins`):
  each plugin's own status, its API card and what it knows of its engine, and for a plugin's own instances the
  figures the Databases view already has of the data folder (how many files, how much on disk: nothing more is
  opened or asked for them). Who is on this database now, by its claims, is listed for the Share form.
- `ask(app, body)`: one form's answer (`POST /api/databases/instances`): test, new, connect, share, port,
  credentials, forget. A change is made only when the page confirmed it (`confirm`), and a refusal that names what
  accepts it (a server off this machine: `accept_remote`) goes back with that name, for the page's second question.
  A password is never logged, never echoed, and taken out of whatever an engine says of its failure.
- `elsewhere(app)`: the file instances outside the data folder, so the Databases view lists them with the folder's
  own and their tables can be looked into."""
from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from . import lib

ACTIONS = ("test", "new", "connect", "share", "port", "credentials", "forget")
SECRETS = ("password", "admin_password")  # of a form: never logged or echoed
HIDDEN = "(not shown)"


class Asked(lib.Refused):
    """A form's answer refused, in the plugin's own words. `accept`: the argument that, sent true with the same form,
    makes the change anyway (the page asks it as a second, explicit confirmation)."""

    def __init__(self, status: int, reason: str, accept: str | None = None):
        super().__init__(status, reason)
        self.accept = accept

    def answer(self) -> dict:
        out = {"error": self.reason}
        if self.accept:
            out["accept"] = self.accept
        return out


def folder_of(app) -> Path:
    """The data folder this integrator's database plugins speak of: beside its database."""
    return Path(app.db_path).parent if getattr(app, "db_path", None) is not None else lib.layout.data_dir()


def plugins(app) -> dict:
    """The database plugins this integrator holds, by name, in their order: each attached here at its first ask when
    nothing attached it yet (the page's process attaches its plugins at its start; a test's app at the first ask), so
    it reads and keeps through this app's login. One another app holds is left to it."""
    found = lib.databases()
    for p in found.values():
        if p.app is None:
            app.attach(p)
    return {name: p for name, p in found.items() if p.app is app}


def _own_figures(plugin, listing: dict) -> dict:
    """What the Databases view's listing already knows of a plugin's own instance: a file engine's files in the data
    folder and their bytes; the server here's folder, and whether it runs."""
    if plugin.SERVER:
        m = listing.get("mongo") or {} if plugin.ENGINE == "mongodb" else {}
        return {"bytes": m.get("disk"), "files": m.get("diskFiles"), "running": m.get("running"), "serverVersion": m.get("version")}
    mine = [e for e in listing.get("entries") or () if e.get("engine") == plugin.ENGINE and e.get("group") != "instances"]
    return {"bytes": sum(e.get("size") or 0 for e in mine), "files": sum(e.get("files", 1) or 0 for e in mine)}


def suites(app) -> list[str]:
    """Who is on this database now, as its claims name them (linux::Ubuntu, windows::NEPTUNE), this one first: what
    the Share form offers. None but this one when the claims cannot be read."""
    me = lib.claims.instance()
    out = [me]
    try:
        if getattr(app, "db_path", None) is not None:
            out += [h.instance for h in lib.claims.held(app.db_path)]
    except Exception:  # noqa: BLE001 - who else is here is a suggestion: the form takes any name
        pass
    return list(dict.fromkeys(out))


def overview(app) -> dict:
    folder = folder_of(app)
    try:
        listing = app.databases.overview()
    except Exception as e:  # noqa: BLE001 - the instances are listed without the folder's figures
        listing = {"error": f"{type(e).__name__}: {e}"}
    rows = []
    for name, p in plugins(app).items():
        try:
            status = p.status(folder)
        except Exception as e:  # noqa: BLE001 - one plugin's trouble is its own: said in its place
            rows.append({"name": name, "title": p.title or name, "about": p.about, "engine": p.ENGINE, "instances": [],
                         "error": f"{type(e).__name__}: {e}"})
            continue
        status["apis"] = lib.apis.as_dicts(p.apis)
        status["apiFacts"] = lib.apis.facts_of(p)
        for row in status["instances"]:
            if row.get("builtin"):
                row.update({k: v for k, v in _own_figures(p, listing).items() if v is not None})
        rows.append(status)
    return {"plugins": rows, "me": lib.claims.instance(), "suites": suites(app), "dataFolder": str(folder),
            "errors": load_errors()}


def load_errors() -> list[str]:
    """The database plugins left out when the plugins were loaded, and why (a driver's package missing, a library too
    old for it): said on the page in place of the plugin."""
    def ours(where: str, why: str) -> bool:
        low = where.lower()
        return why.startswith("database ") or any(f"plugin-integrator-{e}" in low or f"plugin_integrator_{e}" in low
                                                  for e in lib.DATABASE_ENGINES)
    return [f"{where}: {why}" for where, why in lib.plugin_errors() if ours(where, why)][:8]


def elsewhere(app) -> list[dict]:
    """The file instances the database plugins hold outside the data folder (connected, or made at a whole path): each
    {id, plugin, name, title, engine, path}. One inside the folder is found by the folder's own listing."""
    folder = folder_of(app).resolve()
    out: list[dict] = []
    for name, p in plugins(app).items():
        if p.SERVER:
            continue
        try:
            found = p.instances(folder)
        except Exception:  # noqa: BLE001 - listed without them
            continue
        for inst in found:
            if inst.builtin or inst.folder:
                continue
            path = p.path_of(inst, folder)
            if path is None:
                continue
            try:
                inside = folder == path.resolve().parent or folder in path.resolve().parents
            except (OSError, ValueError):
                continue
            if not inside:
                out.append({"id": f"instance:{name}:{inst.name}", "plugin": name, "name": inst.name,
                            "title": inst.title or inst.name, "engine": p.ENGINE, "path": str(path)})
    return out


def _scrubbed(text: str, body: dict) -> str:
    """What an engine said, without the secrets the form carried."""
    for key in SECRETS:
        secret = body.get(key)
        if isinstance(secret, str) and len(secret) >= 3:
            text = text.replace(secret, HIDDEN)
    return text


def ask(app, body: dict) -> dict:
    """One form of the page answered by its plugin; what it said ({"ok", "said", "lines"}). Refused (Asked, or a 404 for
    a plugin or an instance that is not there) in words."""
    text = lambda key: str(body.get(key) or "").strip() if not isinstance(body.get(key), (dict, list)) else ""  # noqa: E731
    name, action = text("plugin"), text("action")
    p = plugins(app).get(name)
    if p is None:
        raise lib.Refused(HTTPStatus.NOT_FOUND, f"no database plugin {name[:40]!r} here")
    if action not in ACTIONS:
        raise lib.Refused(HTTPStatus.BAD_REQUEST, f"an instance is asked one of: {', '.join(ACTIONS)}")
    if action != "test" and body.get("confirm") is not True:
        raise lib.Refused(HTTPStatus.BAD_REQUEST, "a change to an instance is confirmed on the page first")
    folder = folder_of(app)
    holds = body.get("holds") if isinstance(body.get("holds"), (list, str)) else ()
    secret = lambda key: body.get(key) if isinstance(body.get(key), str) else ""  # noqa: E731 - as typed, not stripped
    server = {"port": body.get("port"), "database": text("database"), "tls": body.get("tls") is True,
              "accept_remote": body.get("accept_remote") is True}
    try:
        if action == "test":
            out = p.test(text("name"), folder)
        elif action == "new":
            admin = {"admin_user": text("admin_user"), "admin_password": secret("admin_password")} if text("admin_user") else {}
            out = p.new_database(text("name"), text("where"), holds, text("title"), folder, **server, **admin)
        elif action == "connect":
            out = p.connect_to(text("name"), text("where"), text("method"), holds, text("title"), folder, **server,
                               user=text("user"), password=secret("password"))
        elif action == "share":
            out = p.share(text("name"), text("who"), text("access"), folder)
        elif action == "port":
            out = p.set_port(text("name"), body.get("port"), folder)
        elif action == "credentials":
            out = p.set_credentials(text("name"), text("user"), secret("password"), folder)
        else:
            out = p.forget(text("name"), folder)
    except lib.Refusal as e:
        raise Asked(HTTPStatus.BAD_REQUEST, _scrubbed(str(e), body), getattr(e, "accept", None)) from None
    except lib.NotHere as e:
        raise Asked(HTTPStatus.CONFLICT, str(e)) from None
    except LookupError as e:
        raise lib.Refused(HTTPStatus.NOT_FOUND, str(e)) from None
    except lib.Refused:
        raise
    except Exception as e:  # noqa: BLE001 - an engine's own failure, in its words (a server's refusal, a full disk)
        raise Asked(HTTPStatus.BAD_GATEWAY, _scrubbed(f"{type(e).__name__}: {e}", body)) from None
    if action != "test":
        app.log(f"integrator: {name}: {action} {text('name')}: {out.get('said')}")  # (what a plugin says holds no secret)
        forget = getattr(app.databases, "forget", None)
        if callable(forget):
            forget()  # the folder is listed again at the next ask: a database made or connected shows at once
    return out
