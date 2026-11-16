# Changelog

## 1.12.0 (2026-11-16)

The database plugins' instances on the integrator's page (the user, 2026-11-15: "for the integrator i need plugins for
each type of database and in each plugin can setup either new databases or connections to existing databases using
many different types of IP or IPC methods. each instance in the plugin has it's own configuration how it's shared,
ports, permissions etc"). Needs liminal-libs>=1.61.0 (its database kind: `storage/databases.py`, plugin API 2.3). The
plugins are packages of their own (plugin-integrator-sqlite, -duckdb, -mongodb); with none installed the page is as it
was.
- **The integrator holds the database plugins** (`instances.py`): attached with its login, so what you add to an
  engine's own instances is kept through it.
- **`GET /api/databases/plugins`**: every engine's plugin with its instances as the page draws them: what each
  holds, where it is, the method it is reached by, who else may attach, its state; its API card and what it knows of
  its engine; and for a plugin's own instances the figures the Databases view already has of the data folder (its
  files and their size: nothing more is opened). Who is on this database now, by its claims, is listed for the Share
  form. A database plugin left out when the plugins were loaded is said, with why.
- **`POST /api/databases/instances`**: one of the page's forms answered by its plugin: test, new, connect, share,
  port, credentials, forget. A change is made only once the page confirmed it. A refusal that names what accepts it
  (a server off this machine) goes back with that name, for the page's second question. A password is never logged
  or echoed, and is taken out of whatever an engine says of its failure.
- **The Databases view lists the instances too**: a database made in the data folder's `instances/` has a group of
  its own, and a file connected from outside the data folder is listed with the folder's own, so its tables can be
  looked into like any other's.

## 1.11.0 (2026-11-15)

The integrator on a database that another system holds (the suite a second time inside WSL, on Windows' own files).
Needs liminal-libs>=1.57.0 (its link: a SQLite file on another system's drive is opened by that system alone).
- **The Databases view** opens each SQLite file through the library's link (`storage.link.connect`, read-only), and
  its time limit on a count is the link's (`link.time_limit`), so its figures come from the system that holds the
  files.
- **A fetcher that reads only writes nothing** (LIMINAL_READONLY, as the suite in WSL first comes in). It used to
  write its status, take back the requests of a fetcher before it, and mark the waiting requests failed. Now a
  request is another fetcher's to take, the status in the file stays that fetcher's own, and the command line seals
  every store the process opens (`storage.set_read_only`), as the charts' does.
- **A page that reads only starts and holds no fetcher** (`FetcherLink(held=False)`; `serve --daemon` too): one
  here would have nothing to do. The page shows the status the fetcher that writes on the database left in it.
- **A database that is behind this software** on another system's drive is said at the command line, in the
  library's words (`storage.common.Behind`), and left as it is: its own system brings it up to date. So is a
  helper that cannot be reached (`storage.link.LinkError`: the other system has no link yet). One line, exit 2.
- **A page that cannot be served ends the service.** The page's thread ended on such a database and the process
  stayed up with no page; it now ends with the reason, so whoever keeps it running sees it failed.

## 1.10.0 (2026-11-15)

The fetcher beside another installation's on the same database (the user: "If i run integrator on both sides, there
cannot be any conflicts, so if one symbol is being operated on, the other integrator would have to operate on another
symbol"). Needs liminal-libs>=1.56.0 (its `claims.py`). With one installation on a database nothing changes.
- **The runs going are every system's.** The standing pass looked at lock files, which name a process only its own
  system can look up: from the other system a held run looked dead. It now asks the claims (`claims.feed_runs`) and
  leaves a feed the other installation is fetching.
- **A request waits for a feed fetched elsewhere.** Its feed's run is not started here, where it would be refused, and
  the request says so ("waiting for massive (fetching on linux::Ubuntu)") instead of failing with "its run ended
  without it". That run reads the same stack and takes the symbol next. If it ends without the symbol, the feed's run
  is held here.
- **A fetcher starting takes back only what a fetcher that is gone left.** Each fetcher says it is at work
  (`claims.present`), and the library's `request_reset` leaves the requests another fetcher is collecting. Until now it
  reset every one.
- **A fetcher that is offline or reads only leaves the requests** to a fetcher that can serve them, when one is at
  work on the database. It used to take each and fail it.

## 1.9.1 (2026-11-15)

Found running the suite on Linux (the user: "check for bugs in the linux environment"): the systemd user unit
`liminal-integrator service install` writes had its interpreter's and its database's paths bare. systemd splits those
lines on spaces, so a data folder with a space in its name gave the service half a path and it opened another
database; a percent sign was read as one of systemd's specifiers. The unit's words are now written as systemd reads
them (liminal-libs 1.53.1's `systemd.py`). Needs liminal-libs>=1.53.1. Windows' scheduled task is unchanged.

## 1.9.0 (2026-11-15)

The integrator inherits the login (the user, 2026-11-14: "the platform and integrator inherit the login function, they
are separate login instances, class vs object"): `IntegratorApp.LOGIN`, an object of the login class its frame holds
(liminal-libs 1.52.0 `App.login_object`), its users the integrator's own (the login's folder `integrator`), answered
under /login/ at 8785 by its page's server (liminal-charts' serve_integrator): the page is its sign-in until signed in
there, its lambda at the rail's foot. The data API is not behind it (the chart app's front reads it); nothing is started
for it and it has no port of its own ("i only want ports for liminal-login ; liminal-platform ; liminal-charts ;
liminal-integrator"). LIMINAL_INTEGRATOR_LOGIN "none" or "off": none. Tests keep every login off and apart.

## 1.8.0 (2026-11-08)

The databases themselves on the integrator's page (the user, 2026-11-07: "the integrator will have stats for the
databases themselves, the platform only cares about hardware"): `databases.py`, answered by the integrator's frame
(`IntegratorApp.api`: `GET /api/databases`, the list; `GET /api/databases/detail?id=`, one database), shown by the
charts app's Databases view on the integrator's page (list | the one picked | its specifics, before the rail; the
charts server passes its frame the routes it does not answer).

- Every SQLite and DuckDB file in the data folder (liminal.db, feeds/, datasets/, gov/, the login's, the backups,
  an integrator of its own), its size on disk with its -wal and -shm, its growth an hour, when it was last written
  (the file or its -wal), and each table's rows. A feed's closed months in history/<feed>/ are one entry, their rows
  from the manifest in the feed's SQLite file (counted when each month was copied), so no month file is opened;
  a copy going on and a superseded file are said so.
- A count never scans a large table: counted outright only in a file under 64 MB, or a table its B-tree puts under
  200,000 rows, within 2 s a database; else SQLite's own statistics (sqlite_stat1) when analysed, or an estimate
  from 48 random root-to-leaf paths read straight from the file (Knuth's estimator: within 0.4% of the exact count
  on real files; 139 ms for the 979 GB massive.db's 8.6 billion rows). Any other DuckDB file: its own table
  statistics (`duckdb_tables().estimated_size`), opened read-only.
- Liminal's MongoDB only while it already runs (its port checked, then a ping; never started, never attached to
  its keeper): its databases with dbStats, each collection's count and sizes from `$collStats` (the `collStats`
  command on a server without it), its version and uptime; not running, its folder's size on disk.
- Nothing runs for nobody: no thread of its own; the folder listed (stat calls) at most every 5 s while the page
  asks; a database opened read-only (SQLite `mode=ro` and query-only, DuckDB `read_only`) for the moment its
  figures are read, one at a time, closed at once, its figures kept a minute; a MongoDB client for one read, closed
  after. Growth comes from the sizes the page's own asks sample (at most a minute apart, a little over an hour
  kept): over the last hour, or the span since the page last looked.
- Tests on stand-ins only (conftest's `no_real_databases`: the real openers refuse, MongoDB's port answers
  nothing); the service hands its frame the database (`IntegratorApp(db_path=)`).

## 1.7.0 (2026-11-06)

The integrator as an app of the frame (liminal-libs 1.10.0's `apps.App`; the user: "the app itself
(either chart or integrator) has plugin ABC as well"; "the plugin ABC will enumerate attached plugins and
their API"): `app.IntegratorApp` (integrator, the fetcher's scroll icon, port 8785) holds the stock-data
plugins and the integrator's login, the one authorization interface they read their keys through. The
fetcher's process attaches them at the host's start (`Fetcher.app`, `Fetcher.login`); the page's process
holds one too (`serve_integrator(frame=...)`), so the integrator's page answers `GET /api/interface` with
the plugins attached and their API; the command line reads the settings through the login
(`load_settings(login=)`). The login is the user environment (`EnvironmentLogin`) until a daemon can hold a
login session of its own, so no key changes hands differently yet. The library at 1.11.0 or later.

## 1.6.1 (2026-11-04)

On liminal-libs 1.5.0's classes (Phase 5 of the object-oriented rewrite): the fetcher's workers for the
plugins that fetch on their own are `runner.Runner(store_factory, settings, log).run()` (`run_all`
before), the assessment's delivery scheme `sourcing.Scheme.standing(store, profiles, now)`; the library
at 1.5.0 or later.

## 1.6.0 (2026-11-03)

Two listeners on the machine (the user: "for the webserver / ports, i just integrator, and charts"): the
integrator's process serves its page and the data API itself at LIMINAL_FETCHER_PORT (`lib.page()`: the
charts app's `serve_integrator`, reading the data here) and holds the fetcher host over the pipe through
`service.FetcherLink` (attached at a page's first request, started if none answers, let go once none has
been in touch for LIMINAL_QUIET_SECONDS; the status, a wake and a pass over the pipe). The fetcher host
has no HTTP of its own any more (`fetcher.run_host`: the host and the work alone; its status names the
integrator's page). `serve --until-quiet` ends the server once no page has been in touch for a while:
what the chart app's front starts for itself when nothing answers at the integrator's port. `lib.front()`
is gone (the charts front no longer attaches to the fetcher: it proxies to the integrator).

## 1.5.0 (2026-11-03)

On liminal-libs 1.4.0 and liminal-charts (the library and the charts app renamed: the naming by system, the
user, 2026-11-03: apps `liminal-<app>`, the library `liminal-libs`, plugins `plugin-<app>-<name>`); every
import of `liminal_lib` is `liminal_libs`, the page served is `liminal_charts`'s. The integrator's own name
stays (`liminal-integrator`, `liminal_integrator`, the task `LiminalIntegrator`).

## 1.4.0 (2026-11-03)

The plugins an integrator loads, and integrators of their own (the user, 2026-11-03: "the default case
is to load all plugins, however the integrator can be loaded with select plugins or none"; "multiple
integrators can address databases"). `--plugins twse,tiingo` or `--plugins none` on `serve`, `host`,
`service install` and `service run` (liminal-libs 1.3.1's selection, LIMINAL_PLUGINS_LOADED, inherited by
every process the integrator starts; every plugin found without it); the fetcher's status and log say
which plugins were loaded, which left out and which names nobody answered to (`fetcher status`, the
Fetcher view). `--name NAME` installs or serves an integrator of its own: on its own database
(`store/data/NAME/liminal.db` unless `--db`), its own page port (`--port`, on the service too) and
plugins, as the task `LiminalIntegrator-NAME` (the unit `liminal-integrator-NAME`), its name
(LIMINAL_INTEGRATOR_NAME) in its status; `service status|remove --name NAME` ask after it. The host
`fetcher` stays one per database, the machine's ledgers shared by key. `cli.apply_instance` applies
the three to the process before its settings load (the app's `liminal-charts fetcher|service ...` does the
same); `service.Service(settings, log, daemon, name, port, plugins, db_path)`, `task_name`, `unit_name`,
`command(daemon, name, db_path, port, plugins)`.

## 1.3.0 (2026-11-03)

On liminal-libs 1.3.0 (the class contract, plugin API 2.0: a plugin's capability scan asked for with
`has_scan`). The fetcher's assessment is a class, `fetcher.Assessor(store, settings, now)`: the feed
profiles read once a tick for every request taken and for the standing pass's `next_due`; `assess()`
stays, one assessment on its own. The service is `service.Service(settings, log, daemon)` with
`LogonTask` (Windows) and `UserUnit` (Linux) as its installers; `install`, `remove`, `status` and `run`
stay as the command line's functions. CI tests against the library's and the app's `release/0.2.0`.

## 1.2.3 (2026-11-03)

A listing abroad's plan is one job per feed and resolution, from the feed's earliest era on: the delivery scheme's
eras are the US market's cuts between feeds that do not carry the listing (600519.SS on Tiingo showed three day eras
cut at Massive's and Alpaca's starts).

## 1.2.2 (2026-11-03)

`liminal-integrator request` puts a symbol on the stack under its stored name (`twse:2330` as `2330.TW`, `eur/usd` as
`EURUSD`), as the app's page does, so the stack shows one request however a symbol is typed.

## 1.2.1 (2026-11-03)

An offline copy of the fetcher still assesses a request before failing it, so its page shows which feeds would be
asked (or why none would) without a request being sent: going through the UI plugin by plugin on the offline
copy (the user, 2026-11-03), a request showed only "nothing fetched: offline".

## 1.2.0 (2026-11-02)

A symbol is assessed under its stored ticker however it is typed (`SPCX::NASDAQ`, `EUR/USD`, `TSE:7203`: the
library's `resolve` first; before, the typed text was looked up and a request for `SPCX::NASDAQ` failed). Stocks
listed outside the US (liminal-libs 1.2.0, plugin API 1.12): `7203.T`, `2330.TW`, `600519.SS` go to the feeds
whose plugins carry their exchange, and a listing no feed here carries says so ("no feed set up here carries
XTKS listings"); the standing pass's next due moment counts each feed's listings abroad by their exchanges' days
(`next_due(..., exchanges=store.watch_exchanges())`). Requires liminal-libs 1.2.0.

## 1.1.2 (2026-11-02)

The app is liminal-charts (package `liminal_charts`): the page and the front are imported from there, the extras pass
runs `python -m liminal_charts sync --extras-only` (the library's `host.APP_MODULE`), and the distribution depends on
`liminal-charts`; CI installs it from its renamed repository.

## 1.1.1 (2026-11-02)

On Windows the logon task is registered through the Task Scheduler cmdlets (Register-ScheduledTask, a trigger at
your own logon): `schtasks /Create /SC ONLOGON` answers "Access is denied" without elevation. `service install` says
so when the Task Scheduler refuses.

## 1.1.0 (2026-11-02)

Its page from the browser, like the app's (the user: "i need a way to run it from the browser like the other
liminals"): `liminal-integrator serve` keeps the fetcher's page at its port (8785) through the app's front in
fetcher mode, the fetcher started when a page comes and let go once none has been in touch for a while (its own
page takes a free port, learnt from it), and `service install` keeps that page there from your logon (the task
LiminalIntegrator on Windows, the unit liminal-integrator on Linux). A daemon when you want one (the user: "the
integrator needs to be able to run autonomously in a 'daemon' mode"): `--daemon` on `serve` or `service install`
holds the fetcher for good, started again if it ends, so it collects what it can on its own. `host` runs one
fetcher in the foreground with nothing holding it, and `--port` picks the page's port.

## 1.0.1 (2026-11-02)

A retired symbol (no longer listed) is assessed and held on the feeds that still have its history, so a source
that has it completes it (the user: "if however, the retired stock data is still available on any of the
sources, complete the retired symbol"); nothing of its current session is asked for. The databases live beside
this program in the workspace's `store/data/`.

## 1.0.0 (2026-11-01)

The fetcher as a program of its own: the resident host `fetcher`, a stack of requests in front of its standing
work, the work for each symbol assessed over the plugins set up here, the feeds' runs held until each has served
the symbol, a standing pass once new data can exist, its status for every page, the app's page and data API
served in its process, and the service (`service install`: a task at logon on Windows, a systemd user unit on
Linux) by the user's decision.
