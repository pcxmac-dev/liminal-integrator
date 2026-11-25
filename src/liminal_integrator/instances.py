"""The database plugins' instances on the integrator's page (its Databases view; liminal-integrator 1.12.0, the
library's since 1.15.0).

The user, 2026-11-15: "for the integrator i need plugins for each type of database and in each plugin can setup either
new databases or connections to existing databases using many different types of IP or IPC methods. each instance in
the plugin has it's own configuration how it's shared, ports, permissions etc". The plugins are the library's kind
(liminal_libs.storage.databases: DatabasePlugin, plugin API 2.3; platform plugins since liminal-libs 1.90.0): SQLite's,
DuckDB's, MongoDB's, each a package of its own.

1.15.0 (Monday list item 30, step 4): what this module kept moved to liminal-libs 1.90.0 (apps/databases.py, the
Databases section the platform and the platform core answer), and these are its names, imported, not copies:
- `overview(app)`: every database plugin with its instances as a page draws them, with the integrator's own figures of
  the data folder for a plugin's own instances (the integrator's route answers the platform core's
  `databases_overview`, which offers no change here: the running platform is the one writer);
- `ask(app, body)`: one form's answer by its plugin, in this process (the integrator asks it only for a test: a change
  goes to the platform, IntegratorApp.instance_change);
- `elsewhere(app)`: the file instances outside the data folder, so the Databases view lists them with the folder's own
  and their tables can be looked into;
- `load_errors` and `ours`: the database plugins left out at loading, by their words or their package's name, today's
  (plugin-platform-sqlite) or the one before the rename (plugin-integrator-sqlite)."""
from __future__ import annotations

from liminal_libs.apps.databases import (  # noqa: F401 - the integrator's names for the library's
    ACTIONS, CHANGES, HIDDEN, SECRETS, Asked, ask, elsewhere, folder_of, load_errors, ours, overview, plugins, suites,
    text_of,
)
