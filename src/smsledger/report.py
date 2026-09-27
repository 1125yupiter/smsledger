#!/usr/bin/env python3
"""Render the summary as a standalone HTML page.

Same honest scope as ``summary``: what already happened. No dependencies, no
network, no fonts fetched -- one file you can open, and that stays true offline
because a page about your money should not phone anywhere.

Palette slots and mark specs follow the validated reference palette (blue/orange,
both modes pass every gate). Dark mode is stepped for the dark surface, not an
automatic inversion.
"""
from __future__ import annotations

import argparse
import html
from datetime import date, timedelta
from pathlib import Path

from .i18n import language
from .i18n import t as _
from .paths import HOME
from .summary import (
    PERSONAL, bank_flow, card_flow, label, last_balances, load,
    monthly, top_counterparties, window,
)

STALE_DAYS = 90

CSS = """
*, *::before, *::after { box-sizing: border-box; }
:root, .viz-root {
  color-scheme: light;
  --surface-1: #fcfcfb; --plane: #f9f9f7;
  --text-primary: #0b0b0b; --text-secondary: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --series-1: #2a78d6; --series-2: #eb6834; --warning: #fab219;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])), :root:where(:not([data-theme="light"])) .viz-root {
    color-scheme: dark;
    --surface-1: #1a1a19; --plane: #0d0d0d;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #d95926;
  }
}
:root[data-theme="dark"], :root[data-theme="dark"] .viz-root {
  color-scheme: dark;
  --surface-1: #1a1a19; --plane: #0d0d0d;
  --text-primary: #ffffff; --text-secondary: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --series-1: #3987e5; --series-2: #d95926;
}
html, body { margin: 0; background: var(--plane); color: var(--text-primary); }
.viz-root {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  color: var(--text-primary); padding: 32px 24px 64px; max-width: 1000px; margin: 0 auto;
}
h1 { font-size: 20px; font-weight: 600; margin: 0 0 4px; }
.sub { color: var(--text-secondary); font-size: 13px; margin: 0 0 28px; }
.card {
  background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 10px; padding: 20px 22px; margin-bottom: 20px;
}
h2 { font-size: 14px; font-weight: 600; margin: 0 0 2px; }
.note { color: var(--muted); font-size: 12px; margin: 0 0 18px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 20px; }
.tile { background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 16px 18px; }
.tile .k { color: var(--text-secondary); font-size: 12px; margin-bottom: 6px; }
.tile .v { font-size: 26px; font-weight: 600; line-height: 1.1; }
.tile .u { color: var(--muted); font-size: 11px; margin-top: 4px; }
.legend { display: flex; gap: 16px; font-size: 12px; color: var(--text-secondary); margin-bottom: 14px; }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.dot { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
svg { display: block; width: 100%; height: auto; overflow: visible; }
.gl { stroke: var(--grid); stroke-width: 1; }
.ax { stroke: var(--axis); stroke-width: 1; }
.tick { fill: var(--muted); font-size: 11px; font-variant-numeric: tabular-nums; }
.bar { transition: opacity .12s; }
.hit { fill: transparent; }
g.mark:hover .bar { opacity: .75; }
.rowlbl { fill: var(--text-secondary); font-size: 12px; }
.rowval { fill: var(--text-primary); font-size: 12px; font-variant-numeric: tabular-nums; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--grid); }
th { color: var(--text-secondary); font-weight: 500; font-size: 12px; }
td.n { text-align: right; font-variant-numeric: tabular-nums; }
.stale { color: var(--warning); font-size: 11px; }
details { margin-top: 14px; }
summary { cursor: pointer; color: var(--text-secondary); font-size: 12px; }
.caveat { background: var(--surface-1); border: 1px solid var(--border); border-left: 3px solid var(--warning);
  border-radius: 8px; padding: 16px 20px; font-size: 13px; color: var(--text-secondary); }
.caveat h2 { color: var(--text-primary); }
.caveat li { margin-bottom: 7px; }
.toggle { position: fixed; top: 14px; right: 16px; font-size: 12px; padding: 5px 11px;
  border: 1px solid var(--border); border-radius: 999px; background: var(--surface-1);
  color: var(--text-secondary); cursor: pointer; }
"""

TOGGLE_JS = """
(function () {
  var b = document.getElementById('tg');
  b.addEventListener('click', function () {
    var cur = document.documentElement.getAttribute('data-theme');
    var dark = cur ? cur === 'dark'
                   : matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', dark ? 'light' : 'dark');
  });
})();
"""


def nice_ceiling(peak: float) -> float:
    """Round a value up to 1 / 2 / 2.5 / 5 x 10^n.

    Applied to the tick interval rather than the axis maximum, so every gridline
    lands on a round number. Ticks taken from the raw peak read as noise
    (12,127,964) and nobody checks a bar against a number like that.
    """
    if peak <= 0:
        return 1.0
    mag = 10 ** (len(str(int(peak))) - 1)
    for step in (1, 2, 2.5, 5, 10):
        if peak <= step * mag:
            return step * mag
    return 10 * mag


def compact(n: float) -> str:
    """Axis labels only. Tables and tooltips keep the exact figure."""
    n = float(n)
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= size:
            v = n / size
            return f"{v:.0f}{unit}" if v >= 10 or v == int(v) else f"{v:.1f}{unit}"
    return f"{n:,.0f}"


def esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def won(n: int | float | None) -> str:
    return f"{int(n or 0):,}"


def tile(k: str, v: str, u: str = "") -> str:
    unit = f'<div class="u">{esc(u)}</div>' if u else ""
    return f'<div class="tile"><div class="k">{esc(k)}</div><div class="v">{esc(v)}</div>{unit}</div>'


def grouped_bars(series: list[tuple[str, int, int]]) -> str:
    """Monthly outflow vs inflow. Two series, so a legend plus direct labels."""
    if not series:
        return f'<p class="note">{esc(_("report.months.short"))}</p>'
    W, H, PAD_L, PAD_B, PAD_T = 900, 260, 8, 28, 16
    # Pick the interval first, then the ceiling, so every gridline is a round number.
    steps = 3
    interval = nice_ceiling((max(max(o, i) for _, o, i in series) or 1) / steps)
    peak = interval * steps
    plot_h = H - PAD_B - PAD_T
    slot = (W - PAD_L) / len(series)
    bw = min(28.0, (slot - 10) / 2)
    parts = []
    for gi in range(steps + 1):
        y = PAD_T + plot_h * gi / steps
        parts.append(f'<line class="gl" x1="{PAD_L}" y1="{y:.1f}" x2="{W}" y2="{y:.1f}"/>')
        parts.append(f'<text class="tick" x="{PAD_L}" y="{y - 4:.1f}">{compact(interval * (steps - gi))}</text>')
    for idx, (month, out, inn) in enumerate(series):
        cx = PAD_L + slot * idx + slot / 2
        for j, (val, var, name) in enumerate(((out, "--series-1", "out"), (inn, "--series-2", "in"))):
            # 2px surface gap between adjacent bars, 4px rounded data-end on the baseline
            x = cx - bw - 1 + j * (bw + 2)
            h = max(2.0, plot_h * (val / peak))
            y = PAD_T + plot_h - h
            parts.append(
                f'<g class="mark"><title>{esc(month)} {esc(name)}: {won(val)}</title>'
                f'<rect class="hit" x="{x:.1f}" y="{PAD_T}" width="{bw:.1f}" height="{plot_h}"/>'
                f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                f'rx="4" fill="var({var})"/></g>'
            )
        parts.append(f'<text class="tick" x="{cx:.1f}" y="{H - 10}" text-anchor="middle">{esc(month)}</text>')
    parts.append(f'<line class="ax" x1="{PAD_L}" y1="{PAD_T + plot_h}" x2="{W}" y2="{PAD_T + plot_h}"/>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(_("report.monthly.h"))}">{"".join(parts)}</svg>'


def hbars(rows: list[tuple[str, int, int]]) -> str:
    """Top counterparties. One series, so one color for every bar."""
    if not rows:
        return f'<p class="note">{esc(_("report.where.empty"))}</p>'
    W, ROW, GAP = 900, 26, 6
    lbl_w, val_w = 250, 120
    peak = max(v for _, v, _ in rows) or 1
    track = W - lbl_w - val_w
    H = len(rows) * (ROW + GAP)
    parts = []
    for i, (name, total, count) in enumerate(rows):
        y = i * (ROW + GAP)
        bw = max(2.0, track * (total / peak))
        parts.append(
            f'<g class="mark"><title>{esc(name)}: {won(total)} over {count} transactions</title>'
            f'<rect class="hit" x="0" y="{y}" width="{W}" height="{ROW}"/>'
            f'<text class="rowlbl" x="0" y="{y + ROW * 0.68:.0f}">{esc(name[:34])}</text>'
            f'<rect class="bar" x="{lbl_w}" y="{y + 6}" width="{bw:.1f}" height="{ROW - 12}" '
            f'rx="4" fill="var(--series-1)"/>'
            f'<text class="rowval" x="{W}" y="{y + ROW * 0.68:.0f}" text-anchor="end">{won(total)}</text>'
            f'</g>'
        )
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(_("report.where.h"))}">{"".join(parts)}</svg>'


def build(rows: list[dict], since: str, until: str, redact: bool) -> str:
    personal = [r for r in rows if r.get("kind") in PERSONAL]
    period = window(personal, since, until)
    approve, cancel = card_flow(period)
    out, inn = bank_flow(period)
    total_out = approve - cancel + out

    tiles = "".join([
        tile(_("report.tile.out"), won(total_out), _("report.tile.out.u", count=len(period))),
        tile(_("report.tile.in"), won(inn), _("report.tile.in.u")),
        tile(_("report.tile.net"), won(inn - total_out), _("report.tile.net.u")),
        tile(_("report.tile.card"), won(approve - cancel), _("report.tile.card.u")),
    ])

    # Monthly series: outflow and inflow side by side
    out_by = dict(monthly(personal, months=12))
    in_by: dict[str, int] = {}
    for r in personal:
        if r.get("kind") == "bank_tx" and r.get("dir") and r.get("dir") != "출금" and r.get("date"):
            in_by[r["date"][:7]] = in_by.get(r["date"][:7], 0) + (r.get("amount") or 0)
    months = sorted(set(out_by) | set(in_by))[-12:]
    series = [(m, out_by.get(m, 0), in_by.get(m, 0)) for m in months]

    tops = top_counterparties(period)
    shown = [(label(k, i + 1, redact), v, c) for i, (k, v, c) in enumerate(tops)]

    bals = last_balances(personal)
    today = date.today()
    brows = []
    for tail, (stamp, bal) in sorted(bals.items(), key=lambda kv: kv[1][0], reverse=True):
        try:
            age = (today - date.fromisoformat(stamp[:10])).days
        except ValueError:
            age = 0
        flag = (f'<span class="stale">{esc(_("report.bal.stale", months=age // 30))}</span>'
                if age > STALE_DAYS else "")
        brows.append(f"<tr><td>…{esc(tail)}</td><td class='n'>{won(bal)}</td>"
                     f"<td>{esc(stamp[:16])} {flag}</td></tr>")

    empty_bal = f'<tr><td colspan=3>{esc(_("report.bal.empty"))}</td></tr>'
    table = "".join(
        f"<tr><td>{esc(n)}</td><td class='n'>{won(v)}</td><td class='n'>{c}</td></tr>"
        for n, v, c in shown
    )

    return f"""<!doctype html>
<html lang="{esc(language())}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>smsledger · {esc(since)} – {esc(until)}</title>
<style>{CSS}</style></head>
<body data-palette="#2a78d6,#eb6834">
<button class="toggle" id="tg">{esc(_("report.theme"))}</button>
<div class="viz-root">
  <h1>{esc(_("report.h1"))}</h1>
  <p class="sub">{esc(_("report.sub", since=since, until=until,
                        shown=format(len(period), ","), total=format(len(rows), ",")))}</p>

  <div class="tiles">{tiles}</div>

  <div class="card">
    <h2>{esc(_("report.monthly.h"))}</h2>
    <p class="note">{esc(_("report.monthly.note"))}</p>
    <div class="legend">
      <span><i class="dot" style="background:var(--series-1)"></i>{esc(_("report.legend.out"))}</span>
      <span><i class="dot" style="background:var(--series-2)"></i>{esc(_("report.legend.in"))}</span>
    </div>
    {grouped_bars(series)}
  </div>

  <div class="card">
    <h2>{esc(_("report.where.h"))}</h2>
    <p class="note">{esc(_("report.where.note"))}{
      " " + esc(_("report.where.redacted")) if redact else ""}</p>
    {hbars(shown)}
    <details><summary>{esc(_("report.table.view"))}</summary>
      <table><thead><tr><th>{esc(_("report.table.counterparty"))}</th>
      <th class="n">{esc(_("report.table.total"))}</th>
      <th class="n">{esc(_("report.table.count"))}</th></tr></thead>
      <tbody>{table}</tbody></table>
    </details>
  </div>

  <div class="card">
    <h2>{esc(_("report.bal.h"))}</h2>
    <p class="note">{esc(_("report.bal.note"))}</p>
    <table><thead><tr><th>{esc(_("report.bal.account"))}</th>
    <th class="n">{esc(_("report.bal.balance"))}</th>
    <th>{esc(_("report.bal.asof"))}</th></tr></thead>
    <tbody>{"".join(brows) or empty_bal}</tbody></table>
  </div>

  <div class="caveat">
    <h2>{esc(_("report.caveat.h"))}</h2>
    <ul>
      <li><strong>{esc(_("report.caveat.transfers.b"))}</strong> {esc(_("report.caveat.transfers"))}</li>
      <li><strong>{esc(_("report.caveat.left.b"))}</strong> {esc(_("report.caveat.left"))}</li>
      <li><strong>{esc(_("report.caveat.coming.b"))}</strong> {esc(_("report.caveat.coming"))}</li>
      <li><strong>{esc(_("report.caveat.cat.b"))}</strong> {esc(_("report.caveat.cat"))}</li>
    </ul>
  </div>
</div>
<script>{TOGGLE_JS}</script>
</body></html>
"""


def _main() -> None:
    ap = argparse.ArgumentParser(description="Render the summary as an HTML page")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--month")
    ap.add_argument("--redact", action="store_true",
                    help="replace counterparty names with positions, for sharing")
    ap.add_argument("-o", "--out", help="output path (default $SMSLEDGER_HOME/report.html)")
    a = ap.parse_args()

    until = a.until or date.today().isoformat()
    if a.month:
        since, until = f"{a.month}-01", f"{a.month}-31"
    elif a.since:
        since = a.since
    else:
        since = (date.fromisoformat(until) - timedelta(days=a.days)).isoformat()

    out = Path(a.out) if a.out else HOME / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(load(), since, until, a.redact), encoding="utf-8")
    print(f"wrote {out}")


def _guarded(fn, name):
    """Wrap a CLI entry point so a failure is still findable tomorrow.

    An unhandled traceback goes to a terminal that gets closed. Support requests
    arrive days later, by which time the only question that matters -- what actually
    went wrong -- has no answer anywhere on disk.
    """
    def wrapper():
        try:
            fn()
        except SystemExit:
            raise
        except BaseException as exc:
            import sys as _sys

            from .support import ERRORS, SUPPORT_EMAIL, record_error

            record_error(name, exc)
            print(f"\n{type(exc).__name__}: {exc}", file=_sys.stderr)
            try:
                from .i18n import t as _t

                print(_t("error.recorded", path=ERRORS), file=_sys.stderr)
                print(_t("error.hint", email=SUPPORT_EMAIL), file=_sys.stderr)
            except BaseException:
                # The error path must never raise an error of its own.
                print(f"recorded in {ERRORS}", file=_sys.stderr)
                print(f"python3 -m smsledger support -> {SUPPORT_EMAIL}", file=_sys.stderr)
            raise SystemExit(1)
    return wrapper


main = _guarded(_main, "smsledger-report")


if __name__ == "__main__":
    main()
