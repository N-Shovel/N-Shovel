#!/usr/bin/env python3
"""Render the GitHub contribution calendar as a looping space-shooter SVG.

The contribution board slowly descends like a wave of invaders. A ship at the
bottom slides left and right and shoots every green square. Each bullet's
flight is solved from the board's descent speed, so it meets the bottom edge
of its target exactly as the square pops.

Usage:
  GITHUB_TOKEN=... python contrib_invaders.py <username> <out.svg>
  python contrib_invaders.py --demo <out.svg>      # random data, for previews
"""
import json
import os
import random
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

# ---- layout -------------------------------------------------------------
CELL, GAP = 11, 3
STEP = CELL + GAP
LEFT, TOP = 34, 46                 # top-left of the board at rest
GAP_BELOW = 92                     # space between the board and the ship
SHIP_H = 14

# ---- timing (seconds) ---------------------------------------------------
ENTER = 1.0          # board slides in
FIRST_SHOT = 1.4     # first shot fired
SAME_COL = 0.075     # delay between shots in the same column
MOVE_BASE = 0.11     # time to move to the next column ...
MOVE_PER_COL = 0.018 # ... plus this per extra column travelled
BULLET_SPEED = 430.0 # px/s
DESCENT = 1.6        # px/s the board sinks while under fire
OUTRO = 2.6          # after the last hit: "cleared" banner, fade out
BURST = 0.35         # explosion length

# days roll over at local midnight, not UTC (Philippines, no DST)
TZ = timezone(timedelta(hours=8))

LIGHT = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]
DARK = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

QUERY = """query($login:String!,$from:DateTime!,$to:DateTime!){user(login:$login){
contributionsCollection(from:$from,to:$to){
contributionCalendar{totalContributions weeks{contributionDays{
date weekday contributionCount contributionLevel}}}}}}"""


def fetch(login, token):
    # end the range tonight in local time so today is always on the board
    end = datetime.now(TZ).replace(hour=23, minute=59, second=59, microsecond=0)
    span = {"login": login, "from": (end - timedelta(days=365)).isoformat(), "to": end.isoformat()}
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": span}).encode(),
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


# ---- the choreography ---------------------------------------------------
def plan(weeks):
    """Return (targets, end_of_fire, ship_y, descent_speed).

    The ship clears the board one row at a time, starting with the row
    nearest to it (Saturday), sweeping left->right then right->left.
    """
    board_bottom = TOP + 7 * STEP - GAP
    ship_y = board_bottom + GAP_BELOW          # top of the ship / muzzle
    rows = {}
    for c, w in enumerate(weeks):
        for d in w:
            if d[3] > 0:
                rows.setdefault(d[1], []).append((c, d))
    order, forward = [], True
    for r in sorted(rows, reverse=True):       # bottom row first
        cells = sorted(rows[r], key=lambda x: x[0], reverse=not forward)
        order += cells
        forward = not forward
    if not order:
        return [], FIRST_SHOT + 0.3, ship_y, 0.0

    # fixed shooting speed: the loop gets longer the more squares there are
    fires, t = [], FIRST_SHOT
    for i, (c, _) in enumerate(order):
        if i:
            dist = abs(c - order[i - 1][0])
            t += SAME_COL if dist == 0 else MOVE_BASE + MOVE_PER_COL * (dist - 1)
        fires.append(t)
    descent = DESCENT

    targets = []
    for (c, d), f in zip(order, fires):
        cell_bottom = TOP + d[1] * STEP + CELL
        # board offset at time T is descent * (T - ENTER); solve for when the
        # bullet tip meets the (moving) bottom edge of the cell
        hit = (ship_y - cell_bottom + BULLET_SPEED * f + descent * ENTER) / (BULLET_SPEED + descent)
        hit_y = cell_bottom + descent * (hit - ENTER)
        targets.append({"col": c, "row": d[1], "lvl": d[3], "date": d[0], "n": d[2],
                        "fire": f, "hit": hit, "hit_y": hit_y})
    end = max(x["hit"] for x in targets) + 0.3
    return targets, end, ship_y, descent


def render(login, total, weeks):
    ncols = len(weeks)
    width = LEFT + ncols * STEP + 16
    targets, fire_end, ship_y, descent = plan(weeks)
    height = ship_y + SHIP_H + 30
    period = fire_end + OUTRO
    sink = descent * (fire_end - ENTER)

    def pc(t):
        return f"{max(0.0, min(100.0, t / period * 100)):.4f}%"

    def cx(col):
        return LEFT + col * STEP + CELL / 2

    css = [f"""
svg{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
.bg{{fill:#ffffff}} .t{{fill:#24292f}} .m{{fill:#57606a}} .ship{{fill:#1f6feb}} .ck{{fill:#0969da}}
.e{{fill:{LIGHT[0]}}} {' '.join(f'.l{i}{{fill:{c}}}' for i, c in enumerate(LIGHT) if i)}
.shot{{fill:#cf222e}} .boom{{fill:none;stroke:#bf8700;stroke-width:2}}
@media (prefers-color-scheme:dark){{
 .bg{{fill:#0d1117}} .t{{fill:#e6edf3}} .m{{fill:#8b949e}} .ship{{fill:#58a6ff}} .ck{{fill:#79c0ff}}
 .e{{fill:{DARK[0]}}} {' '.join(f'.l{i}{{fill:{c}}}' for i, c in enumerate(DARK) if i)}
 .shot{{fill:#ff7b72}} .boom{{stroke:#f2cc60}}
}}
.a{{animation-duration:{period:.3f}s;animation-iteration-count:infinite;animation-fill-mode:both;animation-timing-function:linear}}
.boom{{transform-box:fill-box;transform-origin:center}}
#board{{animation-name:board}}
#ship{{animation-name:ship}}
#clear{{animation-name:clear}}
@keyframes board{{
 0%{{transform:translateY(-24px);opacity:0;animation-timing-function:ease-out}}
 {pc(ENTER)}{{transform:translateY(0);opacity:1}}
 {pc(fire_end)}{{transform:translateY({sink:.2f}px);opacity:1}}
 {pc(period - 1.2)}{{transform:translateY({sink:.2f}px);opacity:1}}
 {pc(period - 0.25)},100%{{transform:translateY({sink + 10:.2f}px);opacity:0}}
}}
@keyframes clear{{
 0%,{pc(fire_end + 0.15)}{{opacity:0}}
 {pc(fire_end + 0.35)},{pc(period - 0.5)}{{opacity:1}}
 100%{{opacity:0}}
}}
"""]

    # ship: parked in the middle, glides to each target's column right on time
    mid = LEFT + ncols * STEP / 2
    frames = [(0.0, mid), (ENTER, mid)]
    for tg in targets:
        x = cx(tg["col"])
        prev_t, prev_x = frames[-1]
        if prev_x != x:
            # hold briefly after the last shot, then glide over and fire on arrival
            depart = prev_t + (tg["fire"] - prev_t) * 0.15
            frames.append((depart, prev_x))
        frames.append((tg["fire"], x))
    frames += [(fire_end + 0.8, frames[-1][1]), (fire_end + 2.4, mid), (period, mid)]
    kf = []
    for t, x in frames:
        kf.append(f"{pc(t)}{{transform:translateX({x - mid:.2f}px);"
                  f"animation-timing-function:ease-in-out}}")
    css.append("@keyframes ship{" + "".join(kf) + "}")

    # per-target: the square pops, a bullet flies, a ring bursts
    for i, tg in enumerate(targets):
        f, h = tg["fire"], tg["hit"]
        travel = ship_y - tg["hit_y"]
        css.append(
            f"@keyframes c{i}{{0%,{pc(h)}{{opacity:1}}{pc(h + 0.06)},{pc(period - 0.05)}{{opacity:0}}100%{{opacity:1}}}}"
            f"@keyframes s{i}{{0%,{pc(f - 0.001)}{{opacity:0;transform:translateY(0)}}"
            f"{pc(f)}{{opacity:1;transform:translateY(0)}}"
            f"{pc(h)}{{opacity:1;transform:translateY(-{travel:.2f}px)}}"
            f"{pc(h + 0.001)},100%{{opacity:0;transform:translateY(-{travel:.2f}px)}}}}"
            f"@keyframes b{i}{{0%,{pc(h)}{{opacity:0;transform:scale(.3)}}"
            f"{pc(h + 0.01)}{{opacity:1;transform:scale(.5)}}"
            f"{pc(h + BURST)},100%{{opacity:0;transform:scale(1.9)}}}}")

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="{login}: {total} contributions in the last year, shot down one by one by a spaceship">',
           f"<style>{''.join(css)}</style>",
           f'<rect class="bg" width="{width}" height="{height}" rx="10"/>',
           f'<text class="t" x="{LEFT}" y="24" font-size="13" font-weight="700">'
           f'{total:,} contributions in the last year</text>',
           f'<text class="m" x="{width - 16}" y="24" font-size="11" text-anchor="end">'
           f'{len(targets)} invaders</text>']

    # descending board (month labels, grid, invaders and bursts move together)
    out.append('<g id="board" class="a">')
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
    for c, w in enumerate(weeks):
        for d in w:
            out.append(f'<rect class="e" x="{LEFT + c * STEP}" y="{TOP + d[1] * STEP}" '
                       f'width="{CELL}" height="{CELL}" rx="2"/>')
    for i, tg in enumerate(targets):
        x, y = LEFT + tg["col"] * STEP, TOP + tg["row"] * STEP
        tip = f"{tg['n']} contribution{'s' if tg['n'] != 1 else ''} on {tg['date']}"
        out.append(f'<rect class="l{tg["lvl"]} a" style="animation-name:c{i}" x="{x}" y="{y}" '
                   f'width="{CELL}" height="{CELL}" rx="2"><title>{tip}</title></rect>')
        out.append(f'<circle class="boom a" style="animation-name:b{i}" '
                   f'cx="{x + CELL / 2}" cy="{y + CELL / 2}" r="7"/>')
    out.append("</g>")

    # bullets (fixed to the screen, not the board)
    for i, tg in enumerate(targets):
        out.append(f'<rect class="shot a" style="animation-name:s{i}" x="{cx(tg["col"]) - 1}" '
                   f'y="{ship_y}" width="2" height="6" rx="1"/>')

    # ship, drawn centred on x = mid with its nose at ship_y
    s = ship_y
    out.append(
        f'<g id="ship" class="a">'
        f'<path class="ship" d="M{mid} {s} l3 5 h2 l0 4 h4 l0 5 h-18 l0 -5 h4 l0 -4 h2 z"/>'
        f'<rect class="ck" x="{mid - 1}" y="{s + 6}" width="2" height="3"/></g>')

    # "cleared" banner
    out.append(f'<text id="clear" class="t a" x="{width / 2}" y="{TOP + 7 * STEP + sink + 36}" '
               f'font-size="13" font-weight="700" text-anchor="middle">'
               f'YEAR CLEARED • {total:,} CONTRIBUTIONS</text>')

    out.append(f'<text class="m" x="{LEFT}" y="{height - 10}" font-size="9">'
               f'@{login} · updated {datetime.now(TZ):%b %d, %Y}</text>')
    out.append("</svg>")
    return "\n".join(out), targets, period


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
    svg, targets, period = render(login, total, weeks)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"wrote {path}: {total} contributions, {len(targets)} invaders, {period:.1f}s loop")


if __name__ == "__main__":
    main()
