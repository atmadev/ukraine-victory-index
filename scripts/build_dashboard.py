#!/usr/bin/env python3
"""Генератор HTML-дашборда Victory Index.

Читає data/history.json (єдине джерело правди) і останній звіт у journal/
(лише для блоку ключових подій) та збирає самодостатню сторінку
dashboard/index.html: без зовнішніх запитів, без залежностей поза stdlib.

Запуск:  python3 scripts/build_dashboard.py
"""

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data" / "history.json"
JOURNAL = ROOT / "journal"
OUT = ROOT / "dashboard" / "index.html"

# --- Метадані показників (ваги — з references/methodology.md) -----------------

BALANCE_PARTS = [
    ("military", "Військовий", 0.40),
    ("economic", "Економічний", 0.25),
    ("human", "Людський ресурс", 0.20),
    ("international", "Міжнародна підтримка", 0.15),
]

STRATEGIC_PARTS = [
    ("security", "Гарантії безпеки", 0.40),
    ("eu_rebuild", "ЄС та відбудова", 0.30),
    ("justice", "Справедливість", 0.30),
]

# Короткі підписи для прямих міток на графіках (місце праворуч обмежене).
SHORT = {
    "military": "Військовий",
    "economic": "Економічний",
    "human": "Людський",
    "international": "Міжнародний",
    "security": "Безпека",
    "eu_rebuild": "ЄС",
    "justice": "Справедливість",
}

# Слоти категорійної палітри (перевірені scripts/validate_palette.js зі скіла
# dataviz: усі гейти PASS у світлій і темній темі, порядок слотів не міняти).
SERIES_COLORS = [
    ("--s1", "#2a78d6", "#3987e5"),
    ("--s2", "#eb6834", "#d95926"),
    ("--s3", "#1baf7a", "#199e70"),
    ("--s4", "#eda100", "#c98500"),
    ("--s-total", "#4a3aa7", "#9085e9"),
]

MONTHS_UA = ["січня", "лютого", "березня", "квітня", "травня", "червня",
             "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]


def fail(msg):
    sys.stderr.write("build_dashboard: %s\n" % msg)
    raise SystemExit(1)


def load_history():
    if not HISTORY.exists():
        fail("не знайдено %s — спочатку зроби хоча б один запуск скіла victory-index"
             % HISTORY.relative_to(ROOT))
    try:
        data = json.loads(HISTORY.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail("data/history.json — некоректний JSON: %s" % e)
    entries = data.get("entries") or []
    if not entries:
        fail("data/history.json не містить жодного запису (entries порожній) — "
             "нема з чого будувати дашборд")
    for i, e in enumerate(entries):
        for key in ("date", "balance", "strategic"):
            if key not in e:
                fail("запис #%d у data/history.json без поля '%s'" % (i, key))
    entries.sort(key=lambda e: e["date"])
    return data, entries


def fmt_date_ua(iso):
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    return "%d %s %d" % (d.day, MONTHS_UA[d.month - 1], d.year)


def fmt_short(iso):
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    return "%02d.%02d" % (d.day, d.month)


def num(v, digits=1):
    return ("%.*f" % (digits, v)).replace("-", "−")


def signed(v, digits=1):
    if v > 0:
        return "+" + num(v, digits)
    if v == 0:
        return "0.0" if digits else "0"
    return num(v, digits)


def delta_markup(cur, prev):
    """Дельта до попереднього запуску: стрілка + значення (текст — токенами тексту)."""
    if prev is None:
        return '<span class="delta delta-none">перший запуск</span>'
    d = round(cur - prev, 1)
    if d > 0:
        cls, arrow = "delta-up", "▲"
    elif d < 0:
        cls, arrow = "delta-down", "▼"
    else:
        cls, arrow = "delta-flat", "→"
    return ('<span class="delta %s"><span class="arrow" aria-hidden="true">%s</span>'
            '%s <span class="delta-note">за тиждень</span></span>' % (cls, arrow, signed(d)))


# --- Ключові події з останнього звіту ----------------------------------------

def md_inline_to_html(text):
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
                  r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def latest_journal_events(limit=5):
    files = sorted(JOURNAL.glob("*.md")) if JOURNAL.exists() else []
    if not files:
        return None, []
    path = files[-1]
    lines = path.read_text(encoding="utf-8").splitlines()
    bullets, inside, cur = [], False, None
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = "Ключові події" in line
            continue
        if not inside:
            continue
        if line.startswith("- "):
            if cur:
                bullets.append(cur)
            cur = line[2:].strip()
        elif line.strip() and cur is not None:
            cur += " " + line.strip()
        elif not line.strip() and cur:
            bullets.append(cur)
            cur = None
    if cur:
        bullets.append(cur)
    return path.name, [md_inline_to_html(b) for b in bullets[:limit]]


# --- Компоненти сторінки ------------------------------------------------------

def divergent_bar(value, scale=100.0):
    """Диверджентний індикатор −100…+100 з нулем-паритетом посередині."""
    frac = max(-1.0, min(1.0, value / scale))
    width = abs(frac) * 50.0
    left = 50.0 - width if frac < 0 else 50.0
    side = "neg" if frac < 0 else "pos"
    return ('<div class="track track-div"><div class="track-zero"></div>'
            '<div class="fill fill-%s" style="left:%.3f%%;width:%.3f%%"></div></div>'
            % (side, left, width))


def progress_bar(value):
    frac = max(0.0, min(1.0, value / 100.0))
    return ('<div class="track track-prog">'
            '<div class="fill fill-prog" style="width:%.3f%%"></div></div>' % (frac * 100.0))


def line_chart(entries, series, y_min, y_max, ticks, zero_line, chart_id):
    """Лінійний графік динаміки inline-SVG. Коректний і на 1–2 точках історії."""
    W, H = 820, 320
    PL, PR, PT, PB = 46, 152, 18, 34
    plot_w, plot_h = W - PL - PR, H - PT - PB
    n = len(entries)

    def xf(i):
        if n == 1:
            return PL + plot_w / 2.0
        return PL + plot_w * i / (n - 1)

    def yf(v):
        v = max(y_min, min(y_max, v))
        return PT + plot_h * (1 - (v - y_min) / float(y_max - y_min))

    out = ['<svg class="chart" viewBox="0 0 %d %d" role="img" '
           'preserveAspectRatio="xMidYMid meet" aria-labelledby="%s-t">' % (W, H, chart_id)]
    out.append('<title id="%s-t">Динаміка: %s</title>'
               % (chart_id, ", ".join(s[0] for s in series)))

    for t in ticks:
        y = yf(t)
        cls = "grid grid-zero" if (zero_line and t == 0) else "grid"
        out.append('<line class="%s" x1="%d" y1="%.2f" x2="%.2f" y2="%.2f"/>'
                   % (cls, PL, y, PL + plot_w, y))
        out.append('<text class="tick" x="%d" y="%.2f" text-anchor="end">%s</text>'
                   % (PL - 10, y + 4, num(t, 0 if float(t).is_integer() else 1)))

    step = max(1, (n + 7) // 8)
    for i, e in enumerate(entries):
        if i % step and i != n - 1:
            continue
        out.append('<text class="tick" x="%.2f" y="%d" text-anchor="middle">%s</text>'
                   % (xf(i), H - 12, fmt_short(e["date"])))

    labels = []
    for idx, (name, values, color_var, is_total, short) in enumerate(series):
        pts = [(xf(i), yf(v)) for i, v in enumerate(values)]
        stroke = "var(%s)" % color_var
        if n > 1:
            out.append('<polyline class="line%s" points="%s" stroke="%s" fill="none"/>'
                       % (" line-total" if is_total else "",
                          " ".join("%.2f,%.2f" % p for p in pts), stroke))
        for (px, py), e, v in zip(pts, entries, values):
            out.append('<circle class="dot%s" cx="%.2f" cy="%.2f" r="%s" fill="%s">'
                       '<title>%s — %s: %s</title></circle>'
                       % (" dot-total" if is_total else "", px, py,
                          "5" if is_total else "4.5", stroke,
                          html.escape(fmt_short(e["date"])), html.escape(name), num(v)))
        labels.append([pts[-1][1], pts[-1][0], short, stroke, values[-1], is_total])

    # Розведення підписів по вертикалі, щоб не накладались.
    labels.sort(key=lambda l: l[0])
    min_gap = 17.0
    for i in range(1, len(labels)):
        if labels[i][0] - labels[i - 1][0] < min_gap:
            labels[i][0] = labels[i - 1][0] + min_gap
    overflow = labels[-1][0] - (PT + plot_h) if labels else 0
    if overflow > 0:
        for l in labels:
            l[0] -= overflow
    for y, x, name, stroke, value, is_total in labels:
        out.append('<circle cx="%.2f" cy="%.2f" r="4" fill="%s"/>' % (x + 12, y - 4, stroke))
        out.append('<text class="slabel%s" x="%.2f" y="%.2f">%s %s</text>'
                   % (" slabel-total" if is_total else "", x + 21, y,
                      html.escape(name), num(value)))
    out.append("</svg>")
    return "\n".join(out)


def legend(series):
    items = "".join(
        '<li><span class="swatch" style="background:var(%s)"></span>%s</li>'
        % (color_var, html.escape(name)) for name, _, color_var, _, _ in series)
    return '<ul class="legend">%s</ul>' % items


def history_table(entries):
    head = ("<tr><th scope=\"col\">Дата</th><th scope=\"col\">Баланс сил</th>"
            + "".join("<th scope=\"col\">%s</th>" % l for _, l, _ in BALANCE_PARTS)
            + "<th scope=\"col\">Стратегічний</th>"
            + "".join("<th scope=\"col\">%s</th>" % l for _, l, _ in STRATEGIC_PARTS)
            + "</tr>")
    rows = []
    for e in reversed(entries):
        cells = ["<th scope=\"row\">%s</th>" % fmt_short(e["date"]),
                 "<td><strong>%s</strong></td>" % signed(e["balance"]["total"])]
        cells += ["<td>%s</td>" % signed(e["balance"].get(k, 0.0)) for k, _, _ in BALANCE_PARTS]
        cells.append("<td><strong>%s</strong></td>" % num(e["strategic"]["total"]))
        cells += ["<td>%s</td>" % num(e["strategic"].get(k, 0.0)) for k, _, _ in STRATEGIC_PARTS]
        rows.append("<tr>%s</tr>" % "".join(cells))
    return ('<table class="data-table"><caption>Усі записи історії, від найновішого</caption>'
            '<thead>%s</thead><tbody>%s</tbody></table>' % (head, "".join(rows)))


# --- Стилі --------------------------------------------------------------------

FONTS = ("https://fonts.googleapis.com/css2?"
         "family=Commissioner:wght@400;500;600;700&"
         "family=Literata:opsz,wght@7..72,400;7..72,600&"
         "family=IBM+Plex+Mono:wght@400;600&display=swap")

CSS = """
:root {
  color-scheme: light;
  --bg: #f4f6f7;
  --surface: #ffffff;
  --surface-2: #eaeef1;
  --ink: #14181c;
  --ink-2: #4c555d;
  --ink-3: #79838c;
  --line: #dde3e8;
  --line-strong: #c3ccd4;
  --pos: #2a78d6;
  --neg: #e34948;
  --prog: #1baf7a;
  --s1: #2a78d6;
  --s2: #eb6834;
  --s3: #1baf7a;
  --s4: #eda100;
  --s-total: #4a3aa7;
  --shadow: 0 1px 2px rgba(20, 24, 28, .06), 0 8px 24px -18px rgba(20, 24, 28, .5);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #101416;
    --surface: #191e21;
    --surface-2: #232a2e;
    --ink: #f0f3f5;
    --ink-2: #b4bec6;
    --ink-3: #838f98;
    --line: #2b3338;
    --line-strong: #3c464d;
    --pos: #3987e5;
    --neg: #e66767;
    --prog: #199e70;
    --s1: #3987e5;
    --s2: #d95926;
    --s3: #199e70;
    --s4: #c98500;
    --s-total: #9085e9;
    --shadow: 0 1px 2px rgba(0, 0, 0, .4);
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #101416;
  --surface: #191e21;
  --surface-2: #232a2e;
  --ink: #f0f3f5;
  --ink-2: #b4bec6;
  --ink-3: #838f98;
  --line: #2b3338;
  --line-strong: #3c464d;
  --pos: #3987e5;
  --neg: #e66767;
  --prog: #199e70;
  --s1: #3987e5;
  --s2: #d95926;
  --s3: #199e70;
  --s4: #c98500;
  --s-total: #9085e9;
  --shadow: 0 1px 2px rgba(0, 0, 0, .4);
}

* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: "Literata", Georgia, "Times New Roman", serif;
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}
.wrap {
  max-width: 1080px;
  margin: 0 auto;
  padding: 40px 20px 64px;
  display: flex;
  flex-direction: column;
  gap: 34px;
}
h1, h2, h3, .ui { font-family: "Commissioner", "Segoe UI", system-ui, sans-serif; }
h1 {
  font-size: clamp(30px, 5vw, 44px);
  font-weight: 700;
  letter-spacing: -.02em;
  line-height: 1.1;
  margin: 0;
  text-wrap: balance;
}
h2 {
  font-size: 15px;
  font-weight: 600;
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--ink-2);
  margin: 0 0 14px;
}
h3 { font-size: 17px; font-weight: 600; margin: 0; letter-spacing: -.01em; }
a { color: inherit; text-underline-offset: 2px; text-decoration-color: var(--line-strong); }
a:hover { text-decoration-color: currentColor; }
:focus-visible { outline: 2px solid var(--pos); outline-offset: 2px; border-radius: 3px; }
.mono, .num, .tick, .slabel, .delta, .weight, .data-table td, .data-table th {
  font-family: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
  font-variant-numeric: tabular-nums;
}

header .eyebrow {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 12px;
  letter-spacing: .16em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin: 0 0 10px;
}
header .stamp {
  margin: 14px 0 0;
  font-size: 15px;
  color: var(--ink-2);
}
.disclaimer {
  margin: 4px 0 0;
  padding-left: 14px;
  border-left: 2px solid var(--line-strong);
  color: var(--ink-3);
  font-size: 13px;
  max-width: 62ch;
}

.card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 22px;
  box-shadow: var(--shadow);
}
.heroes { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.hero .scale-note {
  font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 11.5px;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin: 4px 0 0;
}
.hero .value {
  font-family: "Commissioner", system-ui, sans-serif;
  font-variant-numeric: tabular-nums;
  font-size: clamp(46px, 8vw, 68px);
  font-weight: 700;
  letter-spacing: -.03em;
  line-height: 1;
  margin: 18px 0 6px;
}
.hero .caption { color: var(--ink-2); font-size: 14.5px; margin: 12px 0 0; }

.track { position: relative; height: 12px; border-radius: 6px; background: var(--surface-2); overflow: hidden; }
.track-div .track-zero {
  position: absolute; left: 50%; top: -3px; bottom: -3px; width: 2px;
  margin-left: -1px; background: var(--line-strong); z-index: 2;
}
.fill { position: absolute; top: 0; bottom: 0; border-radius: 4px; }
.fill-pos { background: var(--pos); }
.fill-neg { background: var(--neg); }
.fill-prog { background: var(--prog); left: 0; }
.hero .track { height: 16px; }

.delta { font-size: 14px; color: var(--ink-2); display: inline-flex; align-items: baseline; gap: 6px; }
.delta .arrow { font-size: 11px; }
.delta-up .arrow { color: var(--pos); }
.delta-down .arrow { color: var(--neg); }
.delta-note { color: var(--ink-3); font-size: 12px; letter-spacing: .04em; }
.delta-none { color: var(--ink-3); }

.breakdowns { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.rows { display: flex; flex-direction: column; gap: 16px; }
.row .row-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 7px; }
.row .name { font-family: "Commissioner", system-ui, sans-serif; font-size: 15px; }
.row .weight { font-size: 11.5px; color: var(--ink-3); }
.row .num { font-size: 15px; font-weight: 600; }
.row-foot { display: flex; justify-content: space-between; gap: 12px; margin-top: 6px; }
.ends { font-family: "IBM Plex Mono", monospace; font-size: 11px; color: var(--ink-3); }

.chart-block + .chart-block { margin-top: 18px; }
.chart-wrap { overflow-x: auto; }
.chart { width: 100%; min-width: 560px; height: auto; display: block; }
.grid { stroke: var(--line); stroke-width: 1; }
.grid-zero { stroke: var(--line-strong); stroke-width: 1.5; }
.tick { fill: var(--ink-3); font-size: 11px; font-family: "IBM Plex Mono", monospace; }
.line { stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.line-total { stroke-width: 3; }
.dot { stroke: var(--surface); stroke-width: 2; }
.slabel { fill: var(--ink-2); font-size: 11.5px; font-family: "IBM Plex Mono", monospace; }
.slabel-total { fill: var(--ink); font-weight: 600; }
.legend { list-style: none; display: flex; flex-wrap: wrap; gap: 6px 18px; padding: 0; margin: 0 0 10px; }
.legend li {
  display: flex; align-items: center; gap: 7px;
  font-family: "Commissioner", system-ui, sans-serif; font-size: 13px; color: var(--ink-2);
}
.swatch { width: 11px; height: 11px; border-radius: 3px; display: inline-block; }

.events { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 14px; }
.events li { padding-left: 18px; position: relative; font-size: 15px; }
.events li::before {
  content: ""; position: absolute; left: 0; top: 10px;
  width: 7px; height: 7px; border-radius: 2px; background: var(--line-strong);
}
.empty { color: var(--ink-3); }

details.table-view { margin-top: 18px; }
details.table-view summary {
  cursor: pointer; font-family: "Commissioner", system-ui, sans-serif;
  font-size: 14px; color: var(--ink-2);
}
.table-scroll { overflow-x: auto; margin-top: 12px; }
.data-table { border-collapse: collapse; font-size: 12.5px; width: 100%; }
.data-table caption { text-align: left; color: var(--ink-3); font-size: 12px; padding-bottom: 8px; }
.data-table th, .data-table td { padding: 7px 10px; text-align: right; white-space: nowrap; }
.data-table thead th { color: var(--ink-3); font-weight: 400; border-bottom: 1px solid var(--line); text-align: right; }
.data-table tbody th { text-align: left; color: var(--ink-2); font-weight: 600; }
.data-table tbody tr + tr th, .data-table tbody tr + tr td { border-top: 1px solid var(--line); }

footer {
  border-top: 1px solid var(--line);
  padding-top: 18px;
  color: var(--ink-3);
  font-size: 13.5px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 24px;
  justify-content: space-between;
}

@media (max-width: 760px) {
  .heroes, .breakdowns { grid-template-columns: 1fr; }
  .wrap { padding: 28px 16px 48px; gap: 26px; }
}
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
"""


# --- Складання сторінки -------------------------------------------------------

def breakdown_rows(latest, prev, parts, kind):
    out = []
    for key, label, weight in parts:
        cur = float(latest[kind].get(key, 0.0))
        was = float(prev[kind].get(key, 0.0)) if prev and key in prev[kind] else None
        bar = divergent_bar(cur) if kind == "balance" else progress_bar(cur)
        ends = ("<span class=\"ends\">−100</span><span class=\"ends\">0 · паритет</span>"
                "<span class=\"ends\">+100</span>" if kind == "balance"
                else "<span class=\"ends\">0</span><span class=\"ends\">100</span>")
        out.append(
            '<div class="row">'
            '<div class="row-head"><span class="name">%s <span class="weight">вага %.2f</span></span>'
            '<span class="num">%s</span></div>%s'
            '<div class="row-foot">%s</div>'
            '<div class="row-foot" style="margin-top:4px">%s</div>'
            '</div>'
            % (html.escape(label), weight,
               signed(cur) if kind == "balance" else num(cur),
               bar, ends, delta_markup(cur, was)))
    return "\n".join(out)


def balance_axis(entries):
    peak = 0.0
    for e in entries:
        peak = max(peak, abs(float(e["balance"]["total"])))
        for key, _, _ in BALANCE_PARTS:
            peak = max(peak, abs(float(e["balance"].get(key, 0.0))))
    bound = 20.0
    while bound < peak and bound < 100.0:
        bound += 20.0
    bound = min(bound, 100.0)
    ticks = [-bound, -bound / 2, 0.0, bound / 2, bound]
    return -bound, bound, ticks


def build(data, entries):
    latest = entries[-1]
    prev = entries[-2] if len(entries) > 1 else None
    b, s = latest["balance"], latest["strategic"]

    journal_name, events = latest_journal_events()

    y_min, y_max, b_ticks = balance_axis(entries)
    balance_series = [("Баланс сил", [float(e["balance"]["total"]) for e in entries],
                       "--s-total", True, "Баланс")]
    for i, (key, label, _) in enumerate(BALANCE_PARTS):
        balance_series.append((label, [float(e["balance"].get(key, 0.0)) for e in entries],
                               SERIES_COLORS[i][0], False, SHORT[key]))

    strategic_series = [("Стратегічний", [float(e["strategic"]["total"]) for e in entries],
                         "--s-total", True, "Стратегічний")]
    for i, (key, label, _) in enumerate(STRATEGIC_PARTS):
        strategic_series.append((label, [float(e["strategic"].get(key, 0.0)) for e in entries],
                                 SERIES_COLORS[i][0], False, SHORT[key]))

    events_html = ("".join("<li>%s</li>" % e for e in events) if events
                   else '<li class="empty">Останній звіт не містить розділу ключових подій.</li>')

    axis_note = ("Вісь обрізана до ±%s зі шкали −100…+100, щоб дрібні тижневі зрушення "
                 "лишались видимими; нульова лінія — паритет." % num(y_max, 0))

    parts = []
    parts.append('<div class="wrap">')

    parts.append(
        '<header>'
        '<p class="eyebrow">Війна росії проти України · тижневий зріз</p>'
        '<h1>Індекси балансу сил і стратегічного становища</h1>'
        '<p class="stamp">Останній розрахунок: <strong>%s</strong> · записів в історії: %d · '
        'методологія v%s</p>'
        '</header>'
        % (fmt_date_ua(latest["date"]), len(entries),
           html.escape(str(data.get("methodology_version", "—")))))

    parts.append(
        '<section class="heroes">'
        '<article class="card hero">'
        '<h3>Баланс сил</h3>'
        '<p class="scale-note">−100…+100 · 0 = паритет спроможностей</p>'
        '<p class="value">%s</p>'
        '%s'
        '<div class="row-foot"><span class="ends">перевага рф</span>'
        '<span class="ends">перевага України</span></div>'
        '<p class="caption">Плюс — перевага України. Паритет означає не рівність ресурсів, '
        'а рівність спроможності досягати своїх (асиметричних) воєнних цілей.</p>'
        '<p style="margin:10px 0 0">%s</p>'
        '</article>'
        '<article class="card hero">'
        '<h3>Стратегічний індекс</h3>'
        '<p class="scale-note">0…100 · 100 = стійкий вигідний мир</p>'
        '<p class="value">%s</p>'
        '%s'
        '<div class="row-foot"><span class="ends">0 · поразка</span>'
        '<span class="ends">100 · мир досягнуто</span></div>'
        '<p class="caption">Повільний індекс: реагує на структурні й дипломатичні зрушення, '
        'а не на тижневі фронтові зведення. Шкали двох індексів різні й ніколи не '
        'усереднюються між собою.</p>'
        '<p style="margin:10px 0 0">%s</p>'
        '</article>'
        '</section>'
        % (signed(float(b["total"])), divergent_bar(float(b["total"])),
           delta_markup(float(b["total"]), float(prev["balance"]["total"]) if prev else None),
           num(float(s["total"])), progress_bar(float(s["total"])),
           delta_markup(float(s["total"]), float(prev["strategic"]["total"]) if prev else None)))

    parts.append(
        '<section class="breakdowns">'
        '<div class="card"><h2>Баланс сил: під-індекси</h2><div class="rows">%s</div></div>'
        '<div class="card"><h2>Стратегічний: компоненти</h2><div class="rows">%s</div></div>'
        '</section>'
        % (breakdown_rows(latest, prev, BALANCE_PARTS, "balance"),
           breakdown_rows(latest, prev, STRATEGIC_PARTS, "strategic")))

    parts.append(
        '<section class="card chart-block">'
        '<h2>Динаміка балансу сил</h2>%s<div class="chart-wrap">%s</div>'
        '<p class="caption" style="color:var(--ink-3);font-size:13px;margin:10px 0 0">%s</p>'
        '</section>'
        % (legend(balance_series),
           line_chart(entries, balance_series, y_min, y_max, b_ticks, True, "chart-balance"),
           html.escape(axis_note)))

    parts.append(
        '<section class="card chart-block">'
        '<h2>Динаміка стратегічного індексу</h2>%s<div class="chart-wrap">%s</div>'
        '<details class="table-view"><summary>Таблиця всіх значень</summary>'
        '<div class="table-scroll">%s</div></details>'
        '</section>'
        % (legend(strategic_series),
           line_chart(entries, strategic_series, 0.0, 100.0,
                      [0.0, 25.0, 50.0, 75.0, 100.0], False, "chart-strategic"),
           history_table(entries)))

    parts.append(
        '<section class="card"><h2>Ключові події останнього тижня</h2>'
        '<ul class="events">%s</ul>'
        '<p class="caption" style="color:var(--ink-3);font-size:13px">Джерело: звіт '
        '<span class="mono">journal/%s</span>.</p></section>'
        % (events_html, html.escape(journal_name or "—")))

    parts.append(
        '<footer><span>Методологія v%s · ваги і рубрики — '
        '<span class="mono">references/methodology.md</span></span>'
        '<span>Сторінку згенеровано %s зі <span class="mono">data/history.json</span></span>'
        '</footer>' % (html.escape(str(data.get("methodology_version", "—"))),
                       fmt_date_ua(latest["date"])))

    parts.append(
        '<p class="disclaimer">Аматорський хобі-проєкт на основі відкритих джерел, '
        'а не військова аналітика. Цінність — у послідовній динаміці тижнів, а не в '
        'абсолютних числах. Дані про втрати й спроможності сторін мають велику '
        'невизначеність, обидві сторони ведуть інформаційні операції.</p>')

    parts.append('</div>')

    head = ('<title>Victory Index</title>\n'
            '<meta name="description" content="Тижневі індекси балансу сил і '
            'стратегічного становища у війні росії проти України.">\n'
            '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            '<link rel="stylesheet" href="%s">\n'
            '<style>%s</style>' % (FONTS, CSS))
    return head + "\n" + "\n".join(parts) + "\n"


def main():
    data, entries = load_history()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build(data, entries), encoding="utf-8")
    print("dashboard: %s (%d записів, останній %s)"
          % (OUT.relative_to(ROOT), len(entries), entries[-1]["date"]))


if __name__ == "__main__":
    main()
