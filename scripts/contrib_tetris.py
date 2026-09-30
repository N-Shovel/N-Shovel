#!/usr/bin/env python3
"""Render the GitHub contribution calendar as a looping Tetris-style SVG.

Each week column drops in like a falling piece, the finished board flashes
like a line clear, then the blocks fall away and the loop starts again.

Usage:
  GITHUB_TOKEN=... python contrib_tetris.py <username> <out.svg>
  python contrib_tetris.py --demo <out.svg>      # random data, for previews
"""
import json
import os
import random
import sys
import urllib.request
from datetime import date, timedelta

CELL, GAP = 11, 3
STEP = CELL + GAP
LEFT, TOP = 34, 44
PERIOD = 14.0          # seconds for one full loop
DROP_SPREAD = 5.2      # seconds over which the columns drop in

# light / dark palettes: [empty, level1..level4]
LIGHT = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
DARK = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
# Tetris piece colours used for the "active" falling blocks
PIECES = ["#00c8ff", "#ffd500", "#b44cff", "#3ddc5a", "#ff4d4d", "#3d7bff", "#ff9f1c"]

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

QUERY = """query($login:String!){user(login:$login){contributionsCollection{
contributionCalendar{totalContributions weeks{contributionDays{
date weekday contributionCount contributionLevel}}}}}}"""


def fetch(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [[(d["date"], d["weekday"], d["contributionCount"], LEVELS[d["contributionLevel"]])
              for d in w["contributionDays"]] for w in cal["weeks"]]
    return cal["totalContributions"], weeks


def demo():
    random.seed(7)
    start = date.today() - timedelta(days=364)
    start -= timedelta(days=(start.weekday() + 1) % 7)  # back to Sunday
    weeks, total, d = [], 0, start
    while d <= date.today():
        week = []
        for _ in range(7):
            if d > date.today():
                break
            busy = 0.25 + 0.6 * (d.month in (2, 3, 8, 9))
            n = random.choice([1, 2, 3, 5, 8, 12]) if random.random() < busy else 0
            lvl = 0 if n == 0 else 1 if n < 3 else 2 if n < 5 else 3 if n < 9 else 4
            week.append((d.isoformat(), (d.weekday() + 1) % 7, n, lvl))
            total += n
            d += timedelta(days=1)
        weeks.append(week)
    return total, weeks


def pct(t):
    return f"{max(0.0, min(100.0, t / PERIOD * 100)):.3f}%"


def render(login, total, weeks):
    ncols = len(weeks)
    width = LEFT + ncols * STEP + 16
    height = TOP + 7 * STEP + 34
    active = sum(1 for w in weeks for d in w if d[3] > 0)

    css = [f"""
svg{{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif}}
.bg{{fill:#ffffff}} .t{{fill:#24292f}} .m{{fill:#57606a}}
.e{{fill:{LIGHT[0]}}} {' '.join(f'.l{i}{{fill:{c}}}' for i, c in enumerate(LIGHT) if i)}
@media (prefers-color-scheme:dark){{
 .bg{{fill:#0d1117}} .t{{fill:#e6edf3}} .m{{fill:#8b949e}}
 .e{{fill:{DARK[0]}}} {' '.join(f'.l{i}{{fill:{c}}}' for i, c in enumerate(DARK) if i)}
}}
.b{{animation:drop {PERIOD}s cubic-bezier(.5,0,.75,0) infinite both}}
.p{{animation:tint {PERIOD}s linear infinite both}}
.flash{{animation:flash {PERIOD}s linear infinite both}}
"""]
    # keyframes use absolute times so every block loops on the same period;
    # each block's individual start offset is applied with animation-delay.
    fall_h = TOP + 7 * STEP + 20
    css.append(f"""
@keyframes drop{{
 0%{{transform:translateY(-{fall_h}px);opacity:0}}
 1%{{opacity:1}}
 {pct(0.55)}{{transform:translateY(0);opacity:1;animation-timing-function:ease-out}}
 {pct(0.65)}{{transform:translateY(-3px)}}
 {pct(0.75)}{{transform:translateY(0)}}
 {pct(PERIOD - DROP_SPREAD - 1.6)}{{transform:translateY(0);opacity:1;animation-timing-function:ease-in}}
 {pct(PERIOD - DROP_SPREAD - 0.6)}{{transform:translateY({fall_h}px);opacity:0}}
 100%{{transform:translateY({fall_h}px);opacity:0}}
}}
@keyframes tint{{
 0%,{pct(0.5)}{{opacity:1}}
 {pct(1.2)},100%{{opacity:0}}
}}
@keyframes flash{{
 0%,{pct(DROP_SPREAD + 0.9)}{{opacity:0}}
 {pct(DROP_SPREAD + 1.05)}{{opacity:.85}}
 {pct(DROP_SPREAD + 1.3)}{{opacity:0}}
 {pct(DROP_SPREAD + 1.45)}{{opacity:.6}}
 {pct(DROP_SPREAD + 1.8)},100%{{opacity:0}}
}}
""")

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="{login}: {total} contributions in the last year, as falling Tetris blocks">',
           f"<style>{''.join(css)}</style>",
           f'<rect class="bg" width="{width}" height="{height}" rx="10"/>',
           f'<text class="t" x="{LEFT}" y="24" font-size="14" font-weight="600">'
           f'{total:,} contributions in the last year</text>',
           f'<text class="m" x="{width - 16}" y="24" font-size="11" text-anchor="end">'
           f'{active} blocks placed</text>']

    # month labels
    last = None
    for c, w in enumerate(weeks):
        m = w[0][0][5:7]
        if m != last and w[0][0][8:10] <= "07":
            name = date.fromisoformat(w[0][0]).strftime("%b")
            out.append(f'<text class="m" x="{LEFT + c * STEP}" y="{TOP - 7}" font-size="9">{name}</text>')
        last = m
    for r, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        out.append(f'<text class="m" x="{LEFT - 6}" y="{TOP + r * STEP + 9}" font-size="9" '
                   f'text-anchor="end">{name}</text>')

    # empty board
    out.append("<g>")
    for c, w in enumerate(weeks):
        for d in w:
            out.append(f'<rect class="e" x="{LEFT + c * STEP}" y="{TOP + d[1] * STEP}" '
                       f'width="{CELL}" height="{CELL}" rx="2"/>')
    out.append("</g>")

    # falling blocks: one "piece" per week column, bottom cells land first.
    # They are clipped to the board so they appear from its top edge.
    out.append(f'<clipPath id="board"><rect x="{LEFT - 2}" y="{TOP - 2}" '
               f'width="{ncols * STEP + 2}" height="{7 * STEP + 2}"/></clipPath>')
    out.append('<g clip-path="url(#board)">')
    rng = random.Random(len(weeks) * 31 + total)
    for c, w in enumerate(weeks):
        filled = [d for d in w if d[3] > 0]
        if not filled:
            continue
        colour = PIECES[rng.randrange(len(PIECES))]
        base = c / max(1, ncols - 1) * DROP_SPREAD
        for d in sorted(filled, key=lambda d: -d[1]):
            delay = base + (6 - d[1]) * 0.035
            x, y = LEFT + c * STEP, TOP + d[1] * STEP
            tip = f"{d[2]} contribution{'s' if d[2] != 1 else ''} on {d[0]}"
            out.append(
                f'<g class="b" style="animation-delay:{delay:.3f}s">'
                f'<title>{tip}</title>'
                f'<rect class="l{d[3]}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2"/>'
                f'<rect class="p" style="animation-delay:{delay:.3f}s" fill="{colour}" '
                f'x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2"/>'
                f'<rect x="{x + 1}" y="{y + 1}" width="{CELL - 2}" height="2" rx="1" '
                f'fill="#fff" opacity=".25"/></g>')

    out.append("</g>")

    # line-clear flash over the whole board
    out.append(f'<rect class="flash" x="{LEFT - 3}" y="{TOP - 3}" width="{ncols * STEP + 3}" '
               f'height="{7 * STEP + 3}" rx="4" fill="#ffffff"/>')

    # legend
    ly = TOP + 7 * STEP + 18
    out.append(f'<text class="m" x="{LEFT}" y="{ly + 9}" font-size="9">'
               f'@{login} · updated {date.today():%b %d, %Y}</text>')
    lx = width - 16 - 5 * STEP - 60
    out.append(f'<text class="m" x="{lx}" y="{ly + 9}" font-size="9">Less</text>')
    for i in range(5):
        cls = "e" if i == 0 else f"l{i}"
        out.append(f'<rect class="{cls}" x="{lx + 26 + i * STEP}" y="{ly}" '
                   f'width="{CELL}" height="{CELL}" rx="2"/>')
    out.append(f'<text class="m" x="{lx + 30 + 5 * STEP}" y="{ly + 9}" font-size="9">More</text>')
    out.append("</svg>")
    return "\n".join(out)


def main():
    args = sys.argv[1:]
    if len(args) != 2:
        raise SystemExit(__doc__)
    who, path = args
    if who == "--demo":
        login, (total, weeks) = "N-Shovel", demo()
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN is not set")
        login, (total, weeks) = who, fetch(who, token)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(render(login, total, weeks))
    print(f"wrote {path}: {total} contributions, {len(weeks)} weeks")


if __name__ == "__main__":
    main()
