"""Collect 2021-2025 FBS seasons for the line-prediction backtest.

Writes research/data/season-YYYY.json with regular-season games (including
conference championships), College Football Playoff games, closing spreads
and team conference ids. Bowl games outside the playoff are skipped.

ESPN stores a closing-spread field from 2024 on. For earlier seasons only a
per-book `spread` field exists; it is the home-team spread, and whether it is
the opening or closing number is undocumented. validate() reports how well
each season's lines track results so a bad season is visible.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

SITE = 'https://site.api.espn.com/apis/site/v2/sports/football/college-football'
CORE = 'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football'
FBS = set('1 4 5 8 9 15 17 37 151 18 12'.split())
OUT = Path(__file__).resolve().parent / 'data'
EAST = ZoneInfo('America/New_York')
BOOK_ORDER = ('consensus', 'DraftKings', 'ESPN BET')


def fetch(url, cache):
    key = cache / (url.split('//', 1)[1].replace('/', '_').replace('?', '_').replace('&', '_')[:200] + '.json') if cache else None
    if key and key.exists():
        return json.loads(key.read_text())
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'cfb-backtest/1.0'}), timeout=60) as response:
                data = json.load(response)
            break
        except HTTPError as error:
            if error.code in (400, 404):
                data = {}
                break
            if attempt == 3:
                raise
        except OSError:
            if attempt == 3:
                raise
    if key:
        key.write_text(json.dumps(data))
    return data


MAX_SPREAD = 75  # larger values are prices such as -110, which ESPN sometimes stores in spread fields


def spread_value(text):
    if text is None:
        return None
    if str(text).strip().upper() in ('PK', 'PICK', 'EVEN', 'PK0'):
        return 0.0
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and abs(value) < MAX_SPREAD else None


def closing_margin(document):
    """Expected home margin from the best available line, or (None, None)."""
    items = [i for i in document.get('items', []) if 'live' not in i['provider']['name'].lower()]
    rank = lambda i: next((k for k, name in enumerate(BOOK_ORDER) if name.lower() == i['provider']['name'].lower()), len(BOOK_ORDER))
    for item in sorted(items, key=rank):
        close = spread_value(item.get('homeTeamOdds', {}).get('close', {}).get('pointSpread', {}).get('american'))
        if close is not None:
            return -close, item['provider']['name'] + ' close'
    for item in sorted(items, key=rank):
        spread = spread_value(item.get('spread'))
        if spread is not None:
            return -spread, item['provider']['name']
    return None, None


def game_record(event, cache, kind):
    match = event['competitions'][0]
    sides = {entry['homeAway']: entry for entry in match['competitors']}
    home, away = sides['home'], sides['away']
    odds = fetch(f"{CORE}/events/{event['id']}/competitions/{event['id']}/odds", cache)
    margin, provider = closing_margin(odds)
    stamp = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
    headline = (match.get('notes') or [{}])[0].get('headline', '')
    return dict(id=event['id'], kind=kind, week=event.get('week', {}).get('number'),
                date=stamp.date().isoformat(), localDate=stamp.astimezone(EAST).date().isoformat(),
                home=home['id'], away=away['id'], neutral=match['neutralSite'],
                homeScore=int(home['score']), awayScore=int(away['score']),
                leagueGame=match.get('conferenceCompetition', False),
                championship=kind == 'regular' and 'championship' in headline.lower(),
                headline=headline, margin=margin, provider=provider)


def collect(year, cache):
    teams, regular, playoff = {}, [], []

    def note(sides):
        for side in sides.values():
            t = side['team']
            conf = t.get('conferenceId')
            teams.setdefault(t['id'], dict(name=t.get('location', t.get('displayName')), full=t.get('displayName'),
                                           conference=conf, fbs=conf in FBS))

    boards = [fetch(f'{SITE}/scoreboard?dates={year}&seasontype=2&week={w}&groups=80&limit=300', cache) for w in range(1, 17)]
    post = fetch(f'{SITE}/scoreboard?dates={year}&seasontype=3&week=1&groups=80&limit=300', cache)
    events = []
    for board in boards:
        for event in board.get('events', []):
            if event['season']['year'] == year and event['season']['type'] == 2:
                events.append((event, 'regular'))
    for event in post.get('events', []):
        headline = (event['competitions'][0].get('notes') or [{}])[0].get('headline', '').lower()
        if event['season']['year'] == year and event['season']['type'] == 3 and ('playoff' in headline or 'cfp' in headline):
            events.append((event, 'playoff'))
    chosen = []
    for event, kind in events:
        match = event['competitions'][0]
        sides = {entry['homeAway']: entry for entry in match['competitors']}
        if set(sides) != {'home', 'away'} or not event['status']['type']['completed']:
            continue
        note(sides)
        if any(teams[s['team']['id']]['fbs'] for s in sides.values()):
            chosen.append((event, kind))
    with ThreadPoolExecutor(8) as pool:
        records = list(pool.map(lambda item: game_record(item[0], cache, item[1]), chosen))
    for record in records:
        (playoff if record['kind'] == 'playoff' else regular).append(record)
    regular.sort(key=lambda g: (g['date'], g['id']))
    playoff.sort(key=lambda g: (g['date'], g['id']))
    # A playoff game gets the week after the last regular-season week, for ordering only.
    last = max(g['week'] for g in regular)
    for g in playoff:
        g['week'] = last + 1
    payload = dict(season=year, teams=teams, games=regular, playoff=playoff)
    OUT.mkdir(exist_ok=True)
    (OUT / f'season-{year}.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    return payload


def validate(payload):
    games = [g for g in payload['games'] + payload['playoff'] if g['margin'] is not None]
    results = [g['homeScore'] - g['awayScore'] for g in games]
    lines = [g['margin'] for g in games]
    n = len(lines)
    mean_l, mean_r = sum(lines) / n, sum(results) / n
    cov = sum((a - mean_l) * (b - mean_r) for a, b in zip(lines, results))
    corr = cov / math.sqrt(sum((a - mean_l) ** 2 for a in lines) * sum((b - mean_r) ** 2 for b in results))
    mae = sum(abs(a - b) for a, b in zip(lines, results)) / n
    total = len(payload['games']) + len(payload['playoff'])
    champ = sum(g['championship'] for g in payload['games'])
    print(f"{payload['season']}: {total} games, {n} with lines, {len(payload['playoff'])} playoff, {champ} championship; "
          f"line-result corr {corr:.3f}, MAE {mae:.2f}, mean home line {mean_l:+.2f} vs result {mean_r:+.2f}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('years', nargs='*', type=int, default=[2021, 2022, 2023, 2024, 2025])
    parser.add_argument('--cache', type=Path, help='directory for raw ESPN responses')
    args = parser.parse_args()
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)
    for year in args.years:
        validate(collect(year, args.cache))
