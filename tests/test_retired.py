"""A retired symbol is assessed and completed on the feeds that still have its history (the user,
2026-11-02: "if however, the retired stock data is still available on any of the sources, complete
the retired symbol"), and nothing of its current session is asked for."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone

from liminal_integrator import fetcher, lib

NOW = datetime(2026, 11, 3, 15, 0, tzinfo=timezone.utc)


def test_a_retired_symbols_history_is_the_plan_and_its_session_is_not(tmp_path):
    settings = replace(lib.config.load_settings(env={"MASSIVE_API_KEY": "k", "TIINGO_API_KEY": "t"}, env_file=None),
                       db_path=tmp_path / "liminal.db")
    with lib.Store(settings.db_path) as store:
        for feed in ("massive", "tiingo"):
            store.watch(feed, ["ELME"], "minute", exchange="XNYS")
        store.set_retired("ELME", date(2026, 10, 27))
        a = fetcher.assess(store, settings, "ELME", kinds=("bars", "live"), now=NOW)
    assert a.retired == "2026-10-27" and a.feeds and set(a.feeds) <= {"massive", "tiingo"}  # held: its history completed
    assert a.live == [] and a.note == ""  # no current session for it
    assert a.as_dict()["retired"] == "2026-10-27"
