# Changelog

## 1.4.0 (2026-11-03)

The plugins an integrator loads, and integrators of their own (the user, 2026-11-03: "the default case
is to load all plugins, however the integrator can be loaded with select plugins or none"; "multiple
integrators can address databases"). `--plugins twse,tiingo` or `--plugins none` on `serve`, `host`,
`service install` and `service run` (liminal-lib 1.3.1's selection, LIMINAL_PLUGINS_LOADED, inherited by
every process the integrator starts; every plugin found without it); the fetcher's status and log say
which plugins were loaded, which left out and which names nobody answered to (`fetcher status`, the
Fetcher view). `--name NAME` installs or serves an integrator of its own: on its own database
(`store/data/NAME/liminal.db` unless `--db`), its own page port (`--port`, on the service too) and
plugins, as the task `LiminalIntegrator-NAME` (the unit `liminal-integrator-NAME`), its name
(LIMINAL_INTEGRATOR_NAME) in its status; `service status|remove --name NAME` ask after it. The host
`fetcher` stays one per database, the machine's ledgers shared by key. `cli.apply_instance` applies
the three to the process before its settings load (the app's `liminal fetcher|service ...` does the
same); `service.Service(settings, log, daemon, name, port, plugins, db_path)`, `task_name`, `unit_name`,
`command(daemon, name, db_path, port, plugins)`.

## 1.3.0 (2026-11-03)

On liminal-lib 1.3.0 (the class contract, plugin API 2.0: a plugin's capability scan asked for with
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
listed outside the US (liminal-lib 1.2.0, plugin API 1.12): `7203.T`, `2330.TW`, `600519.SS` go to the feeds
whose plugins carry their exchange, and a listing no feed here carries says so ("no feed set up here carries
XTKS listings"); the standing pass's next due moment counts each feed's listings abroad by their exchanges' days
(`next_due(..., exchanges=store.watch_exchanges())`). Requires liminal-lib 1.2.0.

## 1.1.2 (2026-11-02)

The app is liminal-app (package `liminal_app`): the page and the front are imported from there, the extras pass
runs `python -m liminal_app sync --extras-only` (the library's `host.APP_MODULE`), and the distribution depends on
`liminal-app`; CI installs it from its renamed repository.

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
