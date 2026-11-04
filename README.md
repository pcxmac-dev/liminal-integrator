# liminal-integrator

The fetcher of Liminal: the program that collects the market data and serves it. The chart app
([liminal-charts](https://github.com/pcxmac-dev/liminal-charts)) is its client, and funnels every request of
its pages to it; the library both build on is [liminal-libs](https://github.com/pcxmac-dev/liminal-libs).

- A stack of requests in front: a symbol opened in the chart, or asked for on its page or the command
  line, goes first; its standing work queues behind. For each symbol it assesses the work over the
  plugins set up here (what each can give, how far back, how fresh, at what cost in requests) and
  holds the runs of the feeds that deliver it until each has served the symbol.
- A standing pass, hourly while it is up and only once new data can exist (the feeds' calendars and
  publication delays): every feed's run, the closed months' copy, the extras.
- Its page (the data and monitoring views of the chart app, without the chart) at
  `http://127.0.0.1:8785/`, kept there by `liminal-integrator serve` or the service you install at
  your logon, like the chart app at `http://127.0.0.1:8765/`; the fetcher itself runs while a page is
  in touch, started when one comes and let go once none has been for a while.
- A daemon when you want one (`--daemon`, on `serve` or `service install`): the fetcher held for good
  and started again if it ends, so it collects what it can on its own.
- Every plugin found, or the ones you name (`--plugins twse,tiingo`; `--plugins none` for none at all):
  its status says which were loaded and which left out.
- Integrators of their own beside the one and only (`--name paper`): each on its own database
  (`store/data/paper/liminal.db` unless `--db`), with its own page port (`--port`) and plugins, as a
  task or unit of its own (`LiminalIntegrator-paper`).

```
liminal-integrator serve                 # its page in the browser; the fetcher while a page is in touch (Ctrl+C stops)
liminal-integrator serve --daemon        # the same, and the fetcher held for good: it collects on its own
liminal-integrator status                # its stack and state
liminal-integrator request AAPL NQ1!     # ask for symbols (--kinds bars,live; --wait)
liminal-integrator pass                  # a standing pass now
liminal-integrator host                  # one fetcher here, in the foreground, nothing holding it
liminal-integrator service install       # its page from your logon (--daemon: the fetcher held; remove, status, run)
liminal-integrator serve --plugins twse,tiingo             # these plugins alone (none: no plugin at all)
liminal-integrator service install --name paper --port 8786 --plugins none   # an integrator of its own: its database, page, task
liminal-integrator service status --name paper             # ask after it (remove --name paper takes it away)
```

The app's own command line answers the same: `liminal-charts fetcher ...`, `liminal-charts service ...`.

In the workspace this checkout is `store/`, with the databases beside it in `store/data/` (never in git) and the
plugins it loads in `plugins/` (liminal-libs's `layout.py`).
