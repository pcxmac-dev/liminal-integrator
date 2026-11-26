"""What the integrator's own code associates with, for its own External API (1.16.1, Monday list item 17; liminal-libs
1.63.0's App.apis; the user, 2026-11-16: "the external should be all the SDKs/APIs the plugin associates with"; "for
all apps, and all plugins").

What the integrator's own code calls that Liminal does not make, and nothing of its plugins' (each says its own on its
page) nor of the library's: the Databases view's reads (databases.py) of SQLite through Python's sqlite3 and of the
files' own pages, of DuckDB through its Python client, and of Liminal's MongoDB through PyMongo, each only while it
already runs; the service's startup at your logon (service.py), through the Task Scheduler's PowerShell cmdlets on
Windows and a systemd user unit on Linux; Python's signal module, the service's stop; and git, which the Codebase every
app holds reads the workspace with. What the page and the data API work with is the charts' (their own External API),
and the fetcher's pipe and liminal-net are Liminal's own: none is a card here. Imported only when the integrator's own
External API is asked (IntegratorApp.apis), so its start loads nothing more for it.

Every address is one already read on a maker's own page for a card that landed before this one, with that card's day:
SQLite's, Python's sqlite3, DuckDB's and MongoDB's as the database plugins have them (2026-11-16), the ScheduledTasks
cmdlets' and systemd's as the admin plugins have them (2026-11-11), git's and the signal module's as the platform's
apis.py has them (2026-11-17, 2026-11-18). The integrator never fetches any of them. This is the one .py of the
integrator that names an outside host (the user, 2026-10-31: the app's code names no provider's host, links for
people excepted): tests/test_api_views.py holds every other to that."""
from __future__ import annotations

from liminal_libs.apis import Api, Area, Call, Link

_SQLITE = "https://www.sqlite.org/"
_SQLITE3 = "https://docs.python.org/3/library/sqlite3.html"
_DUCKDB = "https://duckdb.org/docs/stable/"
_MONGO = "https://www.mongodb.com/docs/manual/"
_PYMONGO = "https://www.mongodb.com/docs/languages/python/pymongo-driver/current/"
_WS = "?view=windowsserver2025-ps"
_TASKS = "https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/"
_TASKSCHD = "https://learn.microsoft.com/en-us/windows/win32/taskschd/"
_SYSTEMD = "https://www.freedesktop.org/software/systemd/man/latest/"
_SIGNAL = "https://docs.python.org/3/library/signal.html"
_GIT = "https://git-scm.com/docs/"

SQLITE = Api(
    name="SQLite, through Python's sqlite3", maker="The SQLite project; the Python Software Foundation", kind="sdk",
    about=("The Databases view's figures of every SQLite file in the data folder (databases.py): its pages, free pages, "
           "journal mode and user version, and each table's rows, counted when that is cheap, from SQLite's own "
           "statistics (sqlite_stat1) when the file was analysed, else estimated from a few dozen of its B-tree's "
           "pages read straight from the file. Each file is opened read-only and query-only for the moment its "
           "figures are read (the library's storage/link.py opens it, by the system that holds it), and closed at "
           "once; its writers go on."),
    base="every .db, .sqlite and .sqlite3 file in the data folder, and the file instances the database plugins hold",
    version="the SQLite library Python is built with (sqlite3.sqlite_version, shown with each file's figures)",
    auth="none: the file's permissions",
    limits="a count given up after its time (COUNT_BUDGET_S); one database at a time, its figures kept DETAIL_S",
    costs="free (SQLite is in the public domain; Python's sqlite3 module comes with Python)",
    links=(
        Link("SQLite Documentation", _SQLITE + "docs.html", "docs"),
        Link("Python's sqlite3 module (DB-API 2.0 interface for SQLite databases)", _SQLITE3, "reference"),
        Link("Database File Format", _SQLITE + "fileformat2.html", "spec"),
        Link("Write-Ahead Logging", _SQLITE + "wal.html", "guide"),
        Link("Release History Of SQLite", _SQLITE + "changes.html", "changelog"),
        Link("SQLite Copyright (public domain)", _SQLITE + "copyright.html", "terms"),
    ),
    areas=(
        Area("Python's sqlite3 module", "the standard library's interface to SQLite", _SQLITE3,
             covered="every file's figures, on a read-only connection closed after them"),
        Area("Pragmas", "the statements that read and set a database's own settings", _SQLITE + "pragma.html",
             covered="a file's page size, pages, free pages, journal mode and user version; query_only on every "
                     "connection"),
        Area("The database file format", "a database is one file of pages: its header, its B-trees",
             _SQLITE + "fileformat2.html",
             covered="a large table's rows estimated from its B-tree's pages, read from the file with no connection"),
        Area("Write-ahead logging", "the -wal and -shm files beside a database", _SQLITE + "wal.html",
             covered="a file's size counted with its -wal and -shm files"),
    ),
    calls=(
        Call("PRAGMA query_only=ON", "a connection that refuses every write", "Pragmas",
             used="every connection the Databases view opens", docs=_SQLITE + "pragma.html"),
        Call("PRAGMA page_size, page_count, freelist_count, journal_mode, user_version", "a file's own settings and "
             "size", "Pragmas", used="each file's figures", docs=_SQLITE + "pragma.html"),
        Call("SELECT type, name, tbl_name, rootpage, sql FROM sqlite_master", "the schema: tables, indexes and their "
             "root pages", "Python's sqlite3 module", used="each file's tables and where each one's B-tree starts",
             docs=_SQLITE3),
        Call("SELECT tbl, idx, stat FROM sqlite_stat1", "SQLite's own statistics of an analysed file",
             "Python's sqlite3 module", used="a large table's rows, when the file was analysed", docs=_SQLITE3),
        Call("SELECT count(*) FROM <table>", "a table's rows counted", "Python's sqlite3 module",
             used="a table counted outright when that is cheap, given up after its time", docs=_SQLITE3),
        Call("the file's pages, read straight from it", "a B-tree's root-to-leaf paths", "The database file format",
             used="a large table's rows estimated, the pages read and never the table",
             docs=_SQLITE + "fileformat2.html"),
    ),
    verified="2026-11-16")

DUCKDB = Api(
    name="DuckDB", maker="The DuckDB project (duckdb.org)", kind="sdk",
    about=("The Databases view's figures of a DuckDB file that is not a feed's closed month (databases.py): its tables "
           "and their rows from DuckDB's own table statistics, and the DuckDB that answers. A feed's months are listed "
           "from the manifest in its SQLite file, so no month file is opened. A file is opened read-only, with one "
           "thread and 64 MB, for the moment its figures are read, and closed at once; a file a writer holds refuses, "
           "and that is said."),
    base="the .duckdb files of the data folder and the file instances the database plugins hold",
    version="the duckdb package this Python has (pragma_version(), shown with each file's figures)",
    auth="none of its own: a file's rights on its system",
    limits="one process reads and writes a file, or several read it and none writes",
    costs="free (MIT license)",
    links=(
        Link("DuckDB Documentation", _DUCKDB, "docs"),
        Link("Python API", _DUCKDB + "clients/python/overview", "reference"),
        Link("Concurrency", _DUCKDB + "connect/concurrency", "guide"),
        Link("Release Calendar", "https://duckdb.org/release_calendar", "changelog"),
        Link("duckdb/duckdb on GitHub (MIT license)", "https://github.com/duckdb/duckdb", "source"),
    ),
    areas=(
        Area("The Python client", "duckdb.connect(database, read_only, config) and the connection it gives",
             _DUCKDB + "clients/python/overview", covered="every DuckDB file the Databases view opens"),
        Area("Configuration", "a connection's settings, its threads and its memory limit among them",
             _DUCKDB + "configuration/overview", covered="one thread and 64 MB for each connection"),
        Area("Metadata functions", "the duckdb_% table functions: a database's tables and their estimated rows",
             _DUCKDB + "sql/meta/duckdb_table_functions", covered="each file's tables and rows"),
        Area("Pragmas", "statements about the engine itself, its version among them",
             _DUCKDB + "configuration/pragmas", covered="the DuckDB that answers"),
    ),
    calls=(
        Call("duckdb.connect(path, read_only=True, config={'threads': 1, 'memory_limit': '64MB'})",
             "a connection to a database file, for reading", "The Python client",
             used="each DuckDB file's figures", docs=_DUCKDB + "clients/python/overview"),
        Call("SELECT schema_name, table_name, estimated_size, column_count, index_count FROM duckdb_tables() WHERE NOT "
             "internal AND NOT temporary", "a database's own tables", "Metadata functions",
             used="each table's rows, columns and indexes", docs=_DUCKDB + "sql/meta/duckdb_table_functions"),
        Call("SELECT library_version FROM pragma_version()", "the engine's version", "Pragmas",
             used="the DuckDB that answers", docs=_DUCKDB + "configuration/pragmas"),
    ),
    verified="2026-11-16")

MONGODB = Api(
    name="MongoDB, through PyMongo", maker="MongoDB, Inc. (mongodb.com)", kind="sdk",
    about=("The Databases view's figures of Liminal's MongoDB (databases.py), only while the server already runs: a TCP "
           "check of its port first, then a ping, and it is never started to be asked. Its version and uptime, and "
           "each of its databases (not MongoDB's own) with their collections, counts and storage sizes, read on a "
           "client of the server on this machine alone, closed after the question."),
    base="mongodb://127.0.0.1 at Liminal's MongoDB port (liminal_libs.mongo), directConnection",
    version="the server that answers (serverStatus), through PyMongo 4.x",
    auth="none: the server here takes none and listens on this machine alone",
    limits="800 ms to find the server, 5 s for each answer; asked only when the page shows the view",
    costs="free (the server under the SSPL; PyMongo under Apache 2.0)",
    links=(
        Link("MongoDB Database Manual", _MONGO, "docs"),
        Link("PyMongo, the Python driver", _PYMONGO, "sdk"),
        Link("Connection Strings", _MONGO + "reference/connection-string/", "reference"),
        Link("Release Notes", _MONGO + "release-notes/", "changelog"),
        Link("Server Side Public License (SSPL)", "https://www.mongodb.com/legal/licensing/server-side-public-license",
             "terms"),
    ),
    areas=(
        Area("The Python driver (PyMongo)", "MongoClient and what it gives: databases, collections, commands", _PYMONGO,
             covered="one client for each look at the view, closed after it"),
        Area("Database commands", "ping, serverStatus, dbStats: what a server is asked", _MONGO,
             covered="whether it answers, its version, uptime and memory, each database's figures"),
        Area("Storage statistics", "a collection's count and sizes ($collStats)",
             _MONGO + "reference/operator/aggregation/collStats/", covered="each collection's figures"),
    ),
    calls=(
        Call("MongoClient(host, port, serverSelectionTimeoutMS=800, directConnection=True)", "a client of one server",
             "The Python driver (PyMongo)", used="each look at the view while the server runs", docs=_PYMONGO),
        Call("ping", "whether a server answers commands", "Database commands", used="before anything else is asked",
             docs=_MONGO + "reference/command/ping/"),
        Call("serverStatus", "a running server's version, uptime, process and memory", "Database commands",
             used="the server's line of the view", docs=_MONGO + "reference/command/serverStatus/"),
        Call("listDatabases (MongoClient.list_database_names())", "the databases a server has", "Database commands",
             used="each database but MongoDB's own"),
        Call("dbStats", "a database's collections, documents and sizes", "Storage statistics",
             used="each database's figures", docs=_MONGO + "reference/command/dbStats/"),
        Call("listCollections", "a database's collections", "Database commands", used="each database's collections"),
        Call("$collStats with storageStats", "a collection's count and sizes, the first stage of an aggregation",
             "Storage statistics", used="each collection's figures (an older server: the collStats command)",
             docs=_MONGO + "reference/operator/aggregation/collStats/"),
    ),
    verified="2026-11-16")

SCHEDULED_TASKS = Api(
    name="ScheduledTasks (PowerShell)", maker="Microsoft", kind="powershell",
    about=("Windows' Task Scheduler through PowerShell (service.py): `liminal-integrator service install` registers a "
           "task at your logon, as you (LiminalIntegrator, or LiminalIntegrator-<name>), running `liminal-integrator "
           "service run` with pythonw and no window, and starts it; remove, status and start ask the same task. As "
           "you it sees your user environment variables, where the keys live."),
    base="powershell.exe -NoProfile -NonInteractive, the ScheduledTasks module (Windows PowerShell 5.1)",
    version="the ScheduledTasks module of Windows 11 and Windows Server 2025",
    auth="none of its own: a task at your own logon is yours to register, with no administrator",
    limits="",
    costs="free (part of Windows)",
    links=(
        Link("ScheduledTasks module", _TASKS + _WS, "reference"),
        Link("Task Scheduler", _TASKSCHD + "task-scheduler-start-page", "docs"),
        Link("Register-ScheduledTask", _TASKS + "register-scheduledtask" + _WS, "reference"),
        Link("Security contexts for running tasks", _TASKSCHD + "security-contexts-for-running-tasks", "auth"),
    ),
    areas=(
        Area("Defining a task", "its action, trigger and settings", _TASKS + "new-scheduledtaskaction" + _WS,
             covered="the service's command at your logon, no time limit, one instance, on batteries too"),
        Area("Registering and removing", "a task registered on this PC, or unregistered",
             _TASKS + "register-scheduledtask" + _WS, covered="service install and service remove"),
        Area("Running and ending", "a task started now, or every running instance ended",
             _TASKS + "start-scheduledtask" + _WS, covered="the task started once it is registered"),
        Area("Reading tasks", "a task's definition, its state, its last run and result",
             _TASKS + "get-scheduledtask" + _WS, covered="service status: its state, its command, its last run"),
    ),
    calls=(
        Call("New-ScheduledTaskAction -Execute <pythonw> -Argument <words>", "what a task runs", "Defining a task",
             used="service install", docs=_TASKS + "new-scheduledtaskaction" + _WS),
        Call("New-ScheduledTaskTrigger -AtLogOn -User <you>", "a trigger at your logon", "Defining a task",
             used="service install", docs=_TASKS + "new-scheduledtasktrigger" + _WS),
        Call("New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -MultipleInstances IgnoreNew -AllowStartIfOnBatteries "
             "-DontStopIfGoingOnBatteries", "a task's settings", "Defining a task", used="service install",
             docs=_TASKS + "new-scheduledtasksettingsset" + _WS),
        Call("Register-ScheduledTask -Force", "a task registered (replaced with -Force)", "Registering and removing",
             used="service install", docs=_TASKS + "register-scheduledtask" + _WS, writes=True),
        Call("Unregister-ScheduledTask -Confirm:$false", "a task removed", "Registering and removing",
             used="service remove", docs=_TASKS + "unregister-scheduledtask" + _WS, writes=True),
        Call("Start-ScheduledTask", "a task run now", "Running and ending", used="service install, once registered",
             docs=_TASKS + "start-scheduledtask" + _WS, writes=True),
        Call("Get-ScheduledTask", "a task's definition and state", "Reading tasks", used="service status",
             docs=_TASKS + "get-scheduledtask" + _WS),
        Call("Get-ScheduledTaskInfo", "a task's last run time, result and next run", "Reading tasks",
             used="service status", docs=_TASKS + "get-scheduledtaskinfo" + _WS),
    ),
    verified="2026-11-11")

SYSTEMD = Api(
    name="systemd (a user unit)", maker="the systemd project", kind="command",
    about=("On Linux, `liminal-integrator service install` writes a systemd user unit (liminal-integrator.service, or "
           "liminal-integrator-<name>.service, in ~/.config/systemd/user) running `liminal-integrator service run`, "
           "started again on failure and ended with SIGINT, then enables and starts it with systemctl --user; remove "
           "disables it and takes its file away. With lingering (loginctl enable-linger, said in words and never run "
           "here) it runs without a login."),
    base="systemctl --user, as you",
    version="systemd's manual (latest)",
    auth="none: your own user manager",
    limits="",
    costs="free (part of the system)",
    links=(
        Link("systemd's manual pages", _SYSTEMD, "docs"),
        Link("systemctl(1)", _SYSTEMD + "systemctl.html", "reference"),
        Link("systemd.unit(5)", _SYSTEMD + "systemd.unit.html", "reference"),
        Link("systemd.service(5)", _SYSTEMD + "systemd.service.html", "reference"),
        Link("loginctl(1)", _SYSTEMD + "loginctl.html", "reference"),
        Link("systemd's source", "https://github.com/systemd/systemd", "source"),
    ),
    areas=(
        Area("The user manager", "a manager of each signed-in user's own units (systemctl --user)",
             _SYSTEMD + "systemd.html", covered="the integrator's service at your logon, in ~/.config/systemd/user"),
        Area("Unit files", "[Unit], [Service] and [Install]: what runs, its restarts, its signal",
             _SYSTEMD + "systemd.unit.html", covered="ExecStart, Environment=LIMINAL_DB, Restart=on-failure, "
                                                    "RestartSec, KillSignal=SIGINT, WantedBy=default.target"),
        Area("Enabling and starting", "a unit wanted by a target, started now", _SYSTEMD + "systemctl.html",
             covered="service install and service remove"),
        Area("Lingering", "a user's manager started at boot and kept after logout (loginctl enable-linger)",
             _SYSTEMD + "loginctl.html", covered=""),
    ),
    calls=(
        Call("systemctl --user daemon-reload", "the manager reads its unit files again", "Enabling and starting",
             used="service install and remove", docs=_SYSTEMD + "systemctl.html", writes=True),
        Call("systemctl --user enable --now <unit>", "a unit enabled and started", "Enabling and starting",
             used="service install", docs=_SYSTEMD + "systemctl.html", writes=True),
        Call("systemctl --user disable --now <unit>", "a unit disabled and stopped", "Enabling and starting",
             used="service remove", docs=_SYSTEMD + "systemctl.html", writes=True),
        Call("systemctl --user status <unit> --no-pager", "a unit's state and its last lines", "The user manager",
             used="service status", docs=_SYSTEMD + "systemctl.html"),
        Call("loginctl enable-linger <user>", "a user's manager kept from boot to after logout", "Lingering",
             docs=_SYSTEMD + "loginctl.html", writes=True),
    ),
    verified="2026-11-11")

SIGNALS = Api(
    name="Python's signal module", maker="Python Software Foundation", kind="system",
    about=("The system's signals as the integrator's service takes them (service.py, `service run`): SIGINT, SIGTERM, "
           "and SIGBREAK on Windows, end it in good order, the page down and the fetcher let go. On Windows a "
           "console-less pythonw hears none of them, so the service also looks at its stop event "
           "(liminal-stop-integrator, which liminal-signal sets: the library's lifecycle)."),
    base="the signal module, from the service's main thread",
    version="Python 3.12 to 3.15",
    auth="none: the signals the system sends this process",
    limits="none: each handler set once, as the service starts",
    costs="free (the PSF licence)",
    links=(
        Link("signal: set handlers for asynchronous events", _SIGNAL, "docs"),
        Link("Execution of Python signal handlers", _SIGNAL + "#execution-of-python-signal-handlers", "guide"),
        Link("signal(7): an overview of signals", "https://man7.org/linux/man-pages/man7/signal.7.html", "reference"),
    ),
    calls=(
        Call("signal.signal(SIGINT, handler), signal(SIGTERM, handler), signal(SIGBREAK, handler)", "a handler set "
             "for a signal, only from the main thread (ValueError from another); Python runs it later in the main "
             "thread", used="as the service starts: each sets its stop", docs=_SIGNAL + "#signal.signal"),
    ),
    verified="2026-11-18")

GIT = Api(
    name="git", maker="The Git project", kind="command",
    about=("The version control command the integrator's Codebase reads the workspace's git working copies with (the "
           "frame's Codebase, its page's Codebase view; GET /api/codebase, answered by its frame): each one's branch, "
           "the commit checked out, its remote, what is changed and not committed, how far ahead and behind its "
           "upstream as of its last fetch, and its tracked files, counted by language. git is told to take no lock "
           "(GIT_OPTIONAL_LOCKS=0) and to ask nothing at a terminal (GIT_TERMINAL_PROMPT=0); no remote is asked but "
           "on the user's Fetch."),
    base="git, in each working copy of the workspace",
    version="git status's porcelain v2",
    auth="none of its own: a remote's credentials are git's and the user's (asked at no terminal: a fetch that needs "
         "them fails in words)",
    limits="20 s for each command, 90 s for a fetch; read at most once in 10 minutes unless asked fresh",
    costs="free (GPL 2)",
    links=(
        Link("Git reference", _GIT, "reference"),
        Link("git (its environment variables)", _GIT + "git", "reference"),
        Link("git status", _GIT + "git-status", "reference"),
        Link("git log", _GIT + "git-log", "reference"),
        Link("git config", _GIT + "git-config", "reference"),
        Link("git ls-files", _GIT + "git-ls-files", "reference"),
        Link("git fetch", _GIT + "git-fetch", "reference"),
        Link("Install Git", "https://git-scm.com/install/", "tool"),
        Link("git/git", "https://github.com/git/git", "source"),
    ),
    areas=(
        Area("The working copy", "status: the branch, its upstream, ahead and behind, what is changed",
             _GIT + "git-status", covered="each repository's branch, changes and distance from its upstream"),
        Area("History", "log: the commits", _GIT + "git-log",
             covered="the commit checked out: its hash, date and subject"),
        Area("Configuration", "config: the repository's settings", _GIT + "git-config",
             covered="its remote's address (shown with no name or token in it)"),
        Area("The index", "ls-files: the files git tracks", _GIT + "git-ls-files",
             covered="the code counted: the tracked files"),
        Area("Remotes", "fetch: what a remote has", _GIT + "git-fetch",
             covered="Fetch, on the user's click: the remote-tracking branches move, nothing checked out does"),
        Area("Commits, branches and merges", "commit, branch, merge, rebase, push: the repository changed",
             _GIT, covered=""),
    ),
    calls=(
        Call("git status --porcelain=v2 --branch", "the working copy's state and its branch's headers",
             "The working copy", used="Codebase: the branch, ahead and behind, the changes", docs=_GIT + "git-status"),
        Call("git log -1 --format=%h%x1f%cI%x1f%s", "the last commit: its short hash, its date, its subject", "History",
             used="Codebase: the commit checked out", docs=_GIT + "git-log"),
        Call("git config --get remote.NAME.url", "the address of the remote its branch follows (git config's older "
             "mode)", "Configuration", used="Codebase: its remote", docs=_GIT + "git-config"),
        Call("git ls-files -z", "the files git tracks, each ended by a NUL", "The index",
             used="Codebase: the files counted by language", docs=_GIT + "git-ls-files"),
        Call("git config --get-regexp ^remote\\..*\\.url$", "whether the working copy has any remote", "Configuration",
             used="before a fetch: a working copy with no remote is not asked", docs=_GIT + "git-config"),
        Call("git fetch --quiet", "what the remote has (its remote-tracking branches move)", "Remotes",
             used="Fetch, on the user's click (POST /api/codebase/fetch)", docs=_GIT + "git-fetch", writes=True),
    ),
    verified="2026-11-17")

APIS = (SQLITE, DUCKDB, MONGODB, SCHEDULED_TASKS, SYSTEMD, SIGNALS, GIT)
