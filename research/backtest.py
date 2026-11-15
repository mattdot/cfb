"""Backtest market-only VPI and the results-aware line predictor, 2021-2025 (+2026 holdout).

VPI is scripts/ratings.py exactly as the live site runs it: closing spreads
only. The predictor runs the same random-walk filter but also observes every
final score as a noisy margin, week by week. Its job is to say what Vegas will
post next, so it can carry the last week's results into a final ranking when
no later line exists. Every score below uses only information available
before the predicted line existed.

Tests
  weekly     predict each week's closing lines from everything before that week
  champ      freeze before conference championship week, predict those lines
  selection  freeze after championship week (selection day), predict every
             playoff line
  hindsight  final regular-season SOR with opponents rated in hindsight (the
             live default) versus current strength and game-week strength,
             and how far hindsight moves each game's line
Settings are tuned on the weekly test for 2021-2025 only. The freezes and
the 2026 holdout are scored with those settings and never tuned on.

Run: python research/backtest.py            (tune, then report)
     python research/backtest.py --no-tune  (report with the settings below)
"""
import argparse
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import ratings  # noqa: E402

BETA = 0.11295175807571445
FIRST_SCORED_WEEK = 5
HISTORY = [2021, 2022, 2023, 2024, 2025]
VPI_DRIFT = ratings.WEEKLY_DRIFT
PREDICTOR_DRIFT = 2.0
RESULT_NOISE = 5.0          # SD of a final margin around the rating difference, as the filter treats it


def load(year):
    if year == 2026:
        season = json.loads((ROOT / 'data/season.json').read_text())
        membership = json.loads((ROOT / 'data/conferences-2026.json').read_text())
        teams = {t: dict(v, conference=membership.get(t, 'FCS')) for t, v in season['teams'].items()}
        games = [dict(g, championship=False) for g in season['games']]
        return dict(season=2026, teams=teams, games=games, playoff=[], quotes=season['market']['quotes'])
    season = json.loads((ROOT / f'research/data/season-{year}.json').read_text())
    season['quotes'] = []
    return season


def is_cross(season, g):
    teams = season['teams']
    a, b = teams[g['home']], teams[g['away']]
    if not (a['fbs'] and b['fbs']):
        return False
    return a['conference'] != b['conference'] or a['conference'] in ('18', 'Independents')


class Filter:
    """A random-walk state that sees lines, and optionally results, one week at a time."""

    def __init__(self, season, drift, result_noise=None):
        self.state = ratings.State(season['teams'])
        self.drift, self.result_noise = drift, result_noise

    def advance(self, week):
        if week > 1:
            self.state.drift(self.drift)

    def absorb(self, lines, results):
        self.state.observe(lines, [g['margin'] for g in lines], ratings.LINE_NOISE)
        if self.result_noise:
            self.state.observe(results, [g['homeScore'] - g['awayScore'] for g in results], self.result_noise ** 2)


def weekly(season, vpi_drift=VPI_DRIFT, pred_drift=PREDICTOR_DRIFT, result_noise=RESULT_NOISE):
    """(game, vpi_error, predictor_error) for each lined game from FIRST_SCORED_WEEK on."""
    lines = [g for g in season['games'] if g['margin'] is not None] + season['quotes']
    last = max(g['week'] for g in lines)
    vpi = Filter(season, vpi_drift)
    pred = Filter(season, pred_drift, result_noise)
    out = []
    for week in range(1, last + 1):
        vpi.advance(week)
        pred.advance(week)
        batch = [g for g in lines if g['week'] == week]
        if week >= FIRST_SCORED_WEEK:
            out += [(g, vpi.state.predict(g) - g['margin'], pred.state.predict(g) - g['margin']) for g in batch]
        done = [g for g in season['games'] if g['week'] == week]
        vpi.absorb(batch, done)
        pred.absorb(batch, done)
    return out


def frozen(season, through, drift, result_noise=None):
    f = Filter(season, drift, result_noise)
    for week in range(1, through + 1):
        f.advance(week)
        f.absorb([g for g in season['games'] if g['week'] == week and g['margin'] is not None],
                 [g for g in season['games'] if g['week'] == week])
    return f.state


def freeze(season, through, targets):
    vpi = frozen(season, through, VPI_DRIFT)
    pred = frozen(season, through, PREDICTOR_DRIFT, RESULT_NOISE)
    return [(g, vpi.predict(g), pred.predict(g)) for g in targets if g['margin'] is not None]


def rmse(x):
    x = np.asarray(x, dtype=float)
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else float('nan')


def paired_t(a, b):
    """Positive when b has smaller squared errors than a."""
    d = np.asarray(a) ** 2 - np.asarray(b) ** 2
    return float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))) if len(d) > 2 else float('nan')


def tune(seasons):
    global VPI_DRIFT, PREDICTOR_DRIFT, RESULT_NOISE
    print(f'== Tuning on the weekly test, {HISTORY[0]}-{HISTORY[-1]}, weeks >= {FIRST_SCORED_WEEK}')
    best = min((rmse([r[1] for s in seasons for r in weekly(s, vpi_drift=q)]), q) for q in (1, 2, 3, 4, 6, 8, 12))
    for q in (1, 2, 3, 4, 6, 8, 12):
        print(f'  VPI (lines only)  drift {q:>4}: RMSE {rmse([r[1] for s in seasons for r in weekly(s, vpi_drift=q)]):.3f}')
    VPI_DRIFT = best[1]
    grid = []
    for q, sd in itertools.product((1, 1.5, 2, 3, 4), (4, 4.5, 5, 6, 8, 12)):
        grid.append((rmse([r[2] for s in seasons for r in weekly(s, pred_drift=q, result_noise=sd)]), q, sd))
    for q in (1, 1.5, 2, 3, 4):
        print(f'  predictor drift {q:>4}: ' + '  '.join(f'SD{sd}={v:.3f}' for v, qq, sd in grid if qq == q))
    _, PREDICTOR_DRIFT, RESULT_NOISE = min(grid)
    print(f'  -> VPI drift {VPI_DRIFT}; predictor drift {PREDICTOR_DRIFT}, result noise SD {RESULT_NOISE}')


def ranks(state, season):
    values, _ = state.ratings()
    fbs = sorted((t for t in values if season['teams'][t]['fbs']), key=lambda t: -values[t])
    return {t: i + 1 for i, t in enumerate(fbs)}


def sor(season, games, lines, through, mode):
    """SOR probability per FBS team. mode: 'hindsight' (live default), 'current' or 'then'."""
    teams = season['teams']
    fbs = [t for t in teams if teams[t]['fbs']]
    states = ratings.history(lines, teams, through)
    views = ratings.smooth(states) if mode == 'hindsight' else states
    cache = {}
    def view(week):
        key = through if mode == 'current' else week
        if key not in cache:
            r, h = views[key].ratings()
            cache[key] = r, np.mean(sorted((r[t] for t in fbs), reverse=True)[:25]), h
        return cache[key]
    schedules = {}
    for g in games:
        r, ref, h = view(g['week'])
        for team, opp, sign in ((g['home'], g['away'], 1), (g['away'], g['home'], -1)):
            if teams[team]['fbs']:
                venue = 0 if g['neutral'] else sign
                p = 1 / (1 + math.exp(-BETA * (ref - r[opp] + venue * h)))
                schedules.setdefault(team, []).append((p, sign * (g['homeScore'] - g['awayScore']) > 0))
    out = {}
    for team, sched in schedules.items():
        dist = np.array([1.0])
        wins = sum(won for _, won in sched)
        for p, _ in sched:
            dist = np.convolve(dist, [1 - p, p])
        out[team] = float(dist[wins:].sum()) if wins else 1.0
    return out


def hindsight_report(seasons):
    print('\n== Hindsight: final regular-season SOR (championship games excluded, as on the live site)')
    for s in seasons:
        end = min(g['week'] for g in s['games'] if g['championship']) - 1
        games = [g for g in s['games'] if g['week'] <= end]
        lines = [g for g in games if g['margin'] is not None]
        ranked = {}
        for mode in ('hindsight', 'current', 'then'):
            scores = sor(s, games, lines, end, mode)
            ranked[mode] = {t: i + 1 for i, t in enumerate(sorted(scores, key=scores.get))}
        top = [t for t in ranked['hindsight'] if ranked['hindsight'][t] <= 25]
        diff = lambda m: np.mean([abs(ranked['hindsight'][t] - ranked[m][t]) for t in top])
        best = sorted(top, key=lambda t: ranked['hindsight'][t])[:10]
        print(f"  {s['season']}: top-25 mean |rank change| vs current {diff('current'):.1f}, vs game-week {diff('then'):.1f}")
        print('     top 10 (hindsight / current / game-week): ' + ', '.join(
            f"{s['teams'][t]['name']} {ranked['hindsight'][t]}/{ranked['current'][t]}/{ranked['then'][t]}" for t in best))
    print('\n== How far hindsight moves the original line (FBS vs FBS, |hindsight line - closing line|)')
    for s in seasons:
        end = min(g['week'] for g in s['games'] if g['championship']) - 1
        lines = [g for g in s['games'] if g['margin'] is not None and g['week'] <= end]
        smoothed = ratings.smooth(ratings.history(lines, s['teams'], end))
        gaps = {}
        for g in lines:
            if s['teams'][g['home']]['fbs'] and s['teams'][g['away']]['fbs']:
                band = 'weeks 1-4' if g['week'] <= 4 else 'weeks 5-8' if g['week'] <= 8 else 'week 9+'
                gaps.setdefault(band, []).append(abs(smoothed[g['week']].predict(g) - g['margin']))
        print(f"  {s['season']}: " + '  '.join(f'{b} {np.mean(v):.1f}' for b, v in gaps.items()))


def report(seasons, holdout):
    print(f'\n== Weekly test (VPI drift {VPI_DRIFT}; predictor drift {PREDICTOR_DRIFT}, result noise SD {RESULT_NOISE})')
    print(f'  {"season":<8}{"games":>6}{"VPI":>7}{"pred":>7}{"t":>6} | {"cross-conf VPI/pred":<22}| {"after a bye VPI/pred":<22}| calib slope VPI/pred')
    for s in seasons + holdout:
        rows = weekly(s)
        played = {}
        for g in s['games']:
            for t in (g['home'], g['away']):
                played.setdefault(t, set()).add(g['week'])
        cross = [r for r in rows if is_cross(s, r[0])]
        bye = [r for r in rows if any(r[0]['week'] - 1 not in played.get(t, set()) for t in (r[0]['home'], r[0]['away']))]
        line = np.array([r[0]['margin'] for r in rows])
        slope = lambda i: np.polyfit(line + np.array([r[i] for r in rows]), line, 1)[0]
        label = f"{s['season']}{'*' if s in holdout else ''}"
        print(f'  {label:<8}{len(rows):>6}{rmse([r[1] for r in rows]):>7.2f}{rmse([r[2] for r in rows]):>7.2f}'
              f'{paired_t([r[1] for r in rows], [r[2] for r in rows]):>6.1f} | n={len(cross):>3} {rmse([r[1] for r in cross]):.2f}/{rmse([r[2] for r in cross]):.2f}'
              f'{"":<7}| n={len(bye):>3} {rmse([r[1] for r in bye]):.2f}/{rmse([r[2] for r in bye]):.2f}{"":<7}| {slope(1):.3f}/{slope(2):.3f}')
    print('  * 2026 holdout through the current week, never used for tuning. t > 0: predictor better.')

    for title, pick in (('Freeze before championship week: predict championship lines', 'champ'),
                        ('Freeze at selection day: predict playoff lines', 'playoff')):
        print(f'\n== {title}')
        v_all, p_all, briers = [], [], []
        for s in seasons:
            week = min(g['week'] for g in s['games'] if g['championship'])
            if pick == 'champ':
                rows = freeze(s, week - 1, [g for g in s['games'] if g['championship']])
            else:
                rows = freeze(s, week, s['playoff'])
            v = [vm - g['margin'] for g, vm, _ in rows]
            p = [pm - g['margin'] for g, _, pm in rows]
            v_all += v
            p_all += p
            print(f"  {s['season']}: n={len(rows):>2}  VPI {rmse(v):.2f}  predictor {rmse(p):.2f}")
            for g, vm, pm in rows:
                won = g['homeScore'] > g['awayScore']
                prob = lambda m: 1 / (1 + math.exp(-BETA * m))
                briers.append(((prob(vm) - won) ** 2, (prob(pm) - won) ** 2, (prob(g['margin']) - won) ** 2))
                if pick == 'playoff':
                    T = s['teams']
                    print(f"      {T[g['away']]['name']:>16} @ {T[g['home']]['name']:<16} line {g['margin']:+6.1f}  "
                          f"VPI {vm:+6.1f}  predictor {pm:+6.1f}  result {g['homeScore'] - g['awayScore']:+4d}")
        b = np.array(briers)
        print(f'  all : n={len(v_all)}  VPI {rmse(v_all):.2f}  predictor {rmse(p_all):.2f}  paired t {paired_t(v_all, p_all):.1f}')
        print(f'  win-probability Brier (n={len(b)}, SE ~{b[:, 2].std() / math.sqrt(len(b)):.3f}): '
              f'VPI {b[:, 0].mean():.3f}  predictor {b[:, 1].mean():.3f}  closing line {b[:, 2].mean():.3f}')

    print('\n== How far apart are the two final power rankings at selection day?')
    for s in seasons:
        week = min(g['week'] for g in s['games'] if g['championship'])
        rv = ranks(frozen(s, week, VPI_DRIFT), s)
        rp = ranks(frozen(s, week, PREDICTOR_DRIFT, RESULT_NOISE), s)
        top = [t for t in rv if rv[t] <= 25]
        moved = sorted(top, key=lambda t: -abs(rp[t] - rv[t]))[:3]
        print(f"  {s['season']}: top-25 mean |rank change| {np.mean([abs(rp[t] - rv[t]) for t in top]):.1f}; largest "
              + ', '.join(f"{s['teams'][t]['name']} {rv[t]}->{rp[t]}" for t in moved))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-tune', action='store_true')
    args = parser.parse_args()
    history = [load(y) for y in HISTORY]
    if not args.no_tune:
        tune(history)
    report(history, [load(2026)])
    hindsight_report(history)
