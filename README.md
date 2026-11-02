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
- Its own page (the data and monitoring views of the chart app, without the chart) and the data API on
  `http://127.0.0.1:8785/`.
- Up while someone holds it: the chart app while a page is in touch, `liminal-integrator serve`, or the
  service (`liminal-integrator service install`: a task at your logon on Windows, a systemd user unit on
  Linux), which is your decision to let it run unattended. Gone once nobody does.

```
liminal-integrator serve                 # hold it here, its page in the browser (Ctrl+C lets it go)
liminal-integrator status                # its stack and state
liminal-integrator request AAPL NQ1!     # ask for symbols (--kinds bars,live; --wait)
liminal-integrator pass                  # a standing pass now
liminal-integrator service install       # run unattended (remove, status, run)
```

The app's own command line answers the same: `python -m liminal fetcher ...`, `python -m liminal service ...`.
