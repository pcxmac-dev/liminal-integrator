# Changelog

## 1.14.0 (2026-11-24)

An end in good order (Monday list item 38; the shutdown audit of 2026-11-24: "service: ended" was in no day's log, and
the derived-bar build ran on 20-60 minutes past a stop), on liminal-libs 1.87.0's lifecycle:
- **The extras and the auditors end when the fetcher lets go.** `sync --extras-only` and `audit run` are started
  through `lifecycle.spawn(owner="integrator", tied=True)`: written in the process ledger and tied to the fetcher (its
  job object on Windows, PR_SET_PDEATHSIG on Linux), so they end with it however it ends. Spawned children rather than
  held hosts: a host outlives a fetcher that is killed, and the auditors' code is the integrator's, not the hosts'.
  `let_go` (the fetcher's stop) tells each TERM, its own stop event on Windows (`LIMINAL_STOP_EVENT` in its
  environment, a console-less pythonw hears no signal) and SIGTERM elsewhere, waits for both together up to
  `CHILD_STOP_S` (10 s), then kills what is left with its tree (`end_children`). They were left to finish.
- **The auditors stop between series.** `audit run` listens for that stop (`fetcher.listen_for_stop`) and passes it to
  `Sweep.run(stop=)`; stopped, no sweep is begun, the sweep's cursor keeps its place and an audit asked for is left
  open for the next run rather than marked done.
- **The fetcher is a part of its app.** `IntegratorApp.parts()` is the fetcher in the fetcher host's process
  (`Fetcher.signal`: its loop ended and waited for until its runs are let go, its children ended and its store
  closed), and the host's end now stops the integrator's app (`secure=app.stop`): the fetcher's writes secured first,
  then the plugins told together under one deadline and let go. They were left attached at the host's end.
- **The service ends on its stop event.** `service run` / `serve` waits on `Local\liminal-stop-integrator` (which
  liminal-signal sets) as well as SIGINT/SIGTERM, and at its end gives the page's server 5 s to go down, lets the
  fetcher go with a word (a detach: the fetcher host ends at once, where a service that was killed left it waiting
  out its idle time) and stops the page's frame.
- Tests on stand-ins (`test_stopping.py`): a spawn whose children record TERM and KILL (one heeding TERM, one killed at
  the deadline, by a stand-in clock), both on the stop event and on SIGTERM; the app's parts and the host's secure;
  the signal waiting for the run's end; the auditors stopping; a child hearing its event; the service ending on its
  event alone with the fetcher detached.

## 1.13.4 (2026-11-24)

Codebase on the integrator's page (Monday list item 15: "Codebase in the login's, the integrator's and the charts'
pages (the platform has it)"; the user, 2026-11-16: "this class will be added to all the 'apps' just like
connections"):
- The integrator's code base is the library's object its frame holds (`IntegratorApp.codebase`, liminal-libs 1.59.0):
  its repositories, how far each is behind its remote, each language's share, what the integrator runs from (its own
  code, the library, its plugins). Its page draws it as a view of its rail with liminal-charts 0.2.4, which also passes
  the page's `POST /api/codebase/fetch` (the remotes asked, on the user's click) to this frame; until then the page's
  `GET /api/codebase` already reached it and the fetch was a 404.
- A test holds the route's shape through the frame's own server (a workspace of the test's own, a stand-in runner: no
  git runs).

## 1.13.3 (2026-11-24)

The review of 2026-11-21 on your desktop (Monday list item 26), its P3s in the integrator:
- **No auditors' process while another holds their claim.** A fetcher that did not hold the claim `audit` started one
  every minute while the sweep was due, each finding the claim taken (`check_auditors`). While another process holds
  it (a hand-started `audit run`, the other installation's), none is started: the sweep under way there is not due
  here, and an audit asked for waits for the claim to be free.
- **A request for bars and an audit keeps its audit.** Only a request of the audit alone reached the auditors; one
  whose kinds held audit with others (`request --kinds bars,audit`) was fetched and its audit lost. The audit is now
  asked of the auditors as a request of its own, as the page asks it, and the request fetches the rest.
- **A feed run by hand is waited for.** A feed whose run was started by hand on this installation (it holds the claim
  `feed:NAME`) made a request for it fail: the run started for the request was refused, and the request was counted
  as served by no feed. Such a run is now waited for like the other installation's (`waiting for NAME (fetching in
  process PID)`); when it ends without the symbol, the feed's run is held here.
- **A named integrator's logon task on a path with a space.** The task's arguments were joined with plain spaces, so a
  database on such a path was split in two; each is now quoted for Windows (`subprocess.list2cmdline`).
- Three tests no longer assume the auditor and database plugins absent: they hold whichever are installed.

## 1.13.2 (2026-11-24)

The review of 2026-11-21 on your desktop (Monday list item 26): a request could stay assessing until the fetcher
restarted. Once taken (`request_next`), a step after it that raised (a busy database writing its priority, a
feed's run that could not start) left it assessing and out of the fetcher's hands, and `request --wait` waited
for ever. Such a request is now waiting again when trying again can help (the database locked or busy, taken on
the next tick), else failed in the error's words; a write that meets the same busy database is tried again on
the next tick.

## 1.13.1 (2026-11-24)

The review of 2026-11-21 on your desktop (Monday list item 26), checked against the checkout: a page's request could race the quiet watcher. It decided under its lock that no page was in touch,
then let the attachment go and ended the server (`serve --until-quiet`) outside it, so a request in between lost the
fetcher it had just attached to and the server ended under it. The decision and the taking of the attachment are now
one step under the lock (`FetcherLink._quiet_step`), and the server ends only if no page came in touch meanwhile.

## 1.13.0 (2026-11-18)

The auditors: what runs them, and what their page asks (the user, 2026-11-15: "auditors should run if a symbol is
updated, or periodically"; "For the integrator, there needs to be a plugin called auditor and it will manage the
configuration of auditing data"; and 2026-11-18: "an auditor plugin, for auditing sources and maintaining the integrity
of the feeds; for the integrator"). Needs liminal-libs>=1.64.0 (the fetch cache and the auditors: `spool.py`,
`storage/pulls.py`, `auditing.py`; plugin API 2.4). Their options are a package of their own
(plugin-integrator-auditor); without it they keep to the defaults.
- **A pull is audited as it closes**, by the feed's run that made it (the library's). What is left runs in a process
  of its own, `liminal-integrator audit run` (`auditors.py`): the audits asked for, a sweep when one is due, else what
  still waits in the fetch cache. It ends when its work is done or the policy's minutes are spent: nothing stays
  running. One at a time on a database (the claim `audit`), whichever installation starts it. A copy that reads only
  audits nothing.
- **The fetcher starts it** (`Fetcher.check_auditors`): when a request of the kind `audit` waits, and when the sweep is
  due by the policy's interval (looked at once a minute). An audit asked for is on the fetcher's stack like any other
  ask and is said there as handed to the auditors; one whose process ended without finishing it is said as failed.
  The fetcher's status says whether the auditors run.
- **`GET /api/auditor`**: the auditors for their page: the policy as the login has it now (a choice made a moment ago
  counts), the fetch cache by state and size against its cap, the pulls verified so far (counted: a pull that passed
  is not kept in the ledger), the last sweep, whether one is due, the findings, the
  audits asked for, the plugin, and whether a process is at work. A setting that is none of an option's choices is
  said in words, and the defaults apply meanwhile.
- **`POST /api/auditor/run`** `{what: "audit" | "sweep", symbol?}`: what waits in the cache (or one symbol) audited
  now, or a sweep now, asked as a request. A copy that reads only refuses.
- **`liminal-integrator audit run [SYMBOLS...] | sweep | status [--limit N]`**: what the fetcher starts, a sweep now,
  and where the auditors stand in a terminal.
- Every command sets the auditors' policy once it knows its settings (the plugin's, else the defaults).

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
