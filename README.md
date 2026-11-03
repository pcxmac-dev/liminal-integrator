# liminal-integrator

The fetcher of Liminal: the program that collects the market data and serves it. The chart app
([liminal](https://github.com/pcxmac-dev/liminal)) is its client, and funnels every request of its
pages to it; the library both build on is [liminal-lib](https://github.com/pcxmac-dev/liminal-lib).

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

```
liminal-integrator serve                 # its page in the browser; the fetcher while a page is in touch (Ctrl+C stops)
liminal-integrator serve --daemon        # the same, and the fetcher held for good: it collects on its own
liminal-integrator status                # its stack and state
liminal-integrator request AAPL NQ1!     # ask for symbols (--kinds bars,live; --wait)
liminal-integrator pass                  # a standing pass now
liminal-integrator host                  # one fetcher here, in the foreground, nothing holding it
liminal-integrator service install       # its page from your logon (--daemon: the fetcher held; remove, status, run)
```

The app's own command line answers the same: `python -m liminal fetcher ...`, `python -m liminal service ...`.

In the workspace this checkout is `store/`, with the databases beside it in `store/data/` (never in git) and the
plugins it loads in `plugins/` (liminal-lib's `layout.py`).
