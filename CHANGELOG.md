# Changelog

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
