# Changelog

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
