"""Collect 2021-2025 FBS seasons for the line-prediction backtest.

Writes research/data/season-YYYY.json with regular-season games (including
conference championships), College Football Playoff games, closing spreads
and team conference ids. Bowl games outside the playoff are skipped.

Lines prefer DraftKings, the book the live site uses:
  1. DraftKings from ESPN's per-book odds (2021-2023, a few 2025 games)
  2. DraftKings closing spread from CollegeFootballData (2023-2025)
  3. ESPN BET, then ESPN's consensus
  4. Bovada's closing spread from CollegeFootballData, then any other book
ESPN's pre-2024 per-book `spread` field is undocumented, but it matches
Bovada's closing line within 0.2-0.45 points and sits 1.3 points from the
opening line, so it is treated as a close. CollegeFootballData needs an API
key: set CFBD_API_KEY, or let a network proxy inject it. --no-cfbd skips it.
validate() reports how well each season's lines track results.
"""
import os
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
CFBD = 'https://api.collegefootballdata.com'


def fetch(url, cache, headers=None):
    key = cache / (url.split('//', 1)[1].replace('/', '_').replace('?', '_').replace('&', '_')[:200] + '.json') if cache else None
    if key and key.exists():
        return json.loads(key.read_text())
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'cfb-backtest/1.0', **(headers or {})}), timeout=60) as response:
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


def espn_spread(item):
    """Home spread from one ESPN book: its close field, else its single spread field."""
    close = spread_value(item.get('homeTeamOdds', {}).get('close', {}).get('pointSpread', {}).get('american'))
    return close if close is not None else spread_value(item.get('spread'))


def cfbd_lines(year, cache):
    """CollegeFootballData spreads by ESPN event id: {id: (home team id, {book: home spread})}."""
    key = os.environ.get('CFBD_API_KEY', 'proxy-injected')
    out = {}
    for kind in ('regular', 'postseason'):
        for game in fetch(f'{CFBD}/lines?year={year}&seasonType={kind}', cache, {'Authorization': f'Bearer {key}'}) or []:
            books = {line['provider']: spread_value(line.get('spread')) for line in game.get('lines', [])}
            out[str(game['id'])] = (str(game['homeTeamId']), {k: v for k, v in books.items() if v is not None})
    return out


def closing_margin(document, home, cfbd):
    """Expected home margin and its source, following the book priority above."""
    espn = {}
    for item in document.get('items', []):
        name = item['provider']['name']
        if 'live' not in name.lower() and name not in espn:
            value = espn_spread(item)
            if value is not None:
                espn[name] = value
    cf_home, cf = cfbd or (home, {})
    sign = 1 if cf_home == home else -1          # CollegeFootballData can list a neutral-site game the other way round
    cf = {k: sign * v for k, v in cf.items()}
    for source, book in (('ESPN', 'DraftKings'), ('CFBD', 'DraftKings'), ('ESPN', 'ESPN BET'),
                         ('ESPN', 'consensus'), ('CFBD', 'Bovada'), ('CFBD', 'consensus')):
        value = (espn if source == 'ESPN' else cf).get(book)
        if value is not None:
            return -value, f'{book} ({source})'
    for name, value in espn.items():
        return -value, f'{name} (ESPN)'
    return None, None


def game_record(event, cache, kind, cfbd):
    match = event['competitions'][0]
    sides = {entry['homeAway']: entry for entry in match['competitors']}
    home, away = sides['home'], sides['away']
    odds = fetch(f"{CORE}/events/{event['id']}/competitions/{event['id']}/odds", cache)
    margin, provider = closing_margin(odds, home['id'], cfbd.get(event['id']))
    stamp = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
    headline = (match.get('notes') or [{}])[0].get('headline', '')
    return dict(id=event['id'], kind=kind, week=event.get('week', {}).get('number'),
                date=stamp.date().isoformat(), localDate=stamp.astimezone(EAST).date().isoformat(),
                home=home['id'], away=away['id'], neutral=match['neutralSite'],
                homeScore=int(home['score']), awayScore=int(away['score']),
                leagueGame=match.get('conferenceCompetition', False),
                championship=kind == 'regular' and 'championship' in headline.lower(),
                headline=headline, margin=margin, provider=provider)


def collect(year, cache, use_cfbd=True):
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
        cfbd = cfbd_lines(year, cache) if use_cfbd else {}
        records = list(pool.map(lambda item: game_record(item[0], cache, item[1], cfbd), chosen))
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
    parser.add_argument('--cache', type=Path, help='directory for raw API responses')
    parser.add_argument('--no-cfbd', action='store_true', help='skip CollegeFootballData lines')
    args = parser.parse_args()
    if args.cache:
        args.cache.mkdir(parents=True, exist_ok=True)
    for year in args.years:
        validate(collect(year, args.cache, not args.no_cfbd))
