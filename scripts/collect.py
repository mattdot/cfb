"""Collect completed 2026 regular-season games and dated poll releases."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from collections import Counter
import math
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

SITE = 'https://site.api.espn.com/apis/site/v2/sports/football/college-football'
CORE = 'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football'
FBS = set('1 4 5 8 9 15 17 37 151 18 12'.split())
DATA = Path(__file__).resolve().parents[1] / 'data'
EAST = ZoneInfo('America/New_York')


def fetch(url):
    with urlopen(Request(url, headers={'User-Agent': 'cfb-market-sor/1.0'}), timeout=60) as response:
        return json.load(response)


def regular_season_game(event):
    if event['season']['type'] != 2:
        return False
    match = event['competitions'][0]
    kind = match.get('type', {})
    if str(kind.get('id')) in {'41', '42'} or kind.get('abbreviation', '').lower() in {
        'conference championship', 'bowl game'
    }:
        return False
    # ESPN also labels title games as STD, with the designation in the event headline.
    headlines = [note.get('headline', '').lower() for note in match.get('notes', [])
                 if note.get('type') == 'event']
    return not any(title.endswith((' championship', ' championship game'))
                   or title.startswith(('fcs championship -', 'college football playoff'))
                   for title in headlines)


def closing_margin(document):
    for item in sorted(document['items'], key=lambda x: x['provider']['id'] != '100'):
        close = item.get('homeTeamOdds', {}).get('close', {}).get('pointSpread', {})
        if close.get('american') is not None:
            return -float(close['american']), item['provider']['name']
    return None, None


def upcoming_margin(match):
    for odds in sorted(match.get('odds', []), key=lambda o: str(o['provider']['id']) != '100'):
        line = odds.get('pointSpread', {}).get('home', {}).get('close', {}).get('line')
        if line is None and (odds.get('details') or '').upper() not in ('', 'OFF'):
            line = odds.get('spread')
        try:
            spread = 0 if str(line).upper() in ('PK', 'PICK') else float(line)
        except (TypeError, ValueError):
            continue
        if math.isfinite(spread):
            return -spread, odds['provider']['name']
    return None, None


def market_snapshot(schedule, last_week, observed):
    # The Sunday after the main Saturday slate advances the market week.
    # A midweek final or a single rescheduled game cannot advance it early.
    saturdays = Counter()
    for event, _ in schedule.values():
        if event['week']['number'] == last_week:
            day = datetime.fromisoformat(event['date'].replace('Z', '+00:00')).astimezone(EAST).date()
            saturdays[day + timedelta(days=(5-day.weekday()) % 7)] += 1
    saturday = saturdays.most_common(1)[0][0]
    available_weeks = {e['week']['number'] for e, _ in schedule.values()}
    elapsed = (observed.astimezone(EAST).date() - saturday).days
    horizon = last_week + max(0, (elapsed + 6) // 7)
    active = max(w for w in available_weeks if w <= horizon)
    quotes = []
    scheduled = quoted = 0
    for event, sides in schedule.values():
        week = event['week']['number']
        if week > active or event['status']['type']['state'] != 'pre':
            continue
        start = datetime.fromisoformat(event['date'].replace('Z', '+00:00'))
        if start <= observed or event['status']['type']['name'] != 'STATUS_SCHEDULED':
            continue
        scheduled += int(week == active)
        match = event['competitions'][0]
        margin, provider = upcoming_margin(match)
        if margin is None:
            continue
        quoted += int(week == active)
        quotes.append(dict(id=event['id'], week=week, home=sides['home']['id'],
                           away=sides['away']['id'], neutral=match['neutralSite'],
                           margin=margin, provider=provider, kickoff=event['date']))
    return dict(asOf=observed.isoformat(timespec='seconds'), activeWeek=active,
                scheduled=scheduled, quoted=quoted, quotes=quotes)


def collect(cache):
    def read(key, url):
        file = cache / key if cache else None
        return json.loads(file.read_text()) if file and file.exists() else fetch(url)

    def scoreboard(week):
        return read(f'w{week}', f'{SITE}/scoreboard?dates=2026&seasontype=2&week={week}&groups=80&limit=200')

    old = json.loads((DATA / 'season.json').read_text()) if (DATA / 'season.json').exists() else {}
    saved = {g['id']: g for g in old.get('games', [])}
    teams, events, schedule = {}, {}, {}
    with ThreadPoolExecutor(8) as pool:
        for board in pool.map(scoreboard, range(1, 17)):
            for event in board['events']:
                if event['season']['year'] != 2026 or not regular_season_game(event):
                    continue
                match = event['competitions'][0]
                sides = {entry['homeAway']: entry for entry in match['competitors']}
                if not all(k in sides for k in ('home','away')):
                    continue
                for side in sides.values():
                    t = side['team']
                    teams[t['id']] = dict(name=t['location'], full=t['displayName'], fbs=t.get('conferenceId') in FBS)
                if any(teams[s['id']]['fbs'] for s in sides.values()):
                    schedule[event['id']] = event, sides
                    if event['status']['type']['completed']:
                        events[event['id']] = event, sides

        def game(item):
            key, (event, sides) = item
            home, away = sides['home'], sides['away']
            old_game = saved.get(key, {})
            if old_game.get('margin') is not None:
                margin, provider = old_game['margin'], old_game['provider']
            else:
                odds = read('o'+key, f'{CORE}/events/{key}/competitions/{key}/odds')
                margin, provider = closing_margin(odds)
            stamp = datetime.fromisoformat(event['date'].replace('Z','+00:00'))
            return dict(id=key, week=event['week']['number'], date=stamp.date().isoformat(),
                        localDate=stamp.astimezone(EAST).date().isoformat(), home=home['id'], away=away['id'],
                        neutral=event['competitions'][0]['neutralSite'], homeScore=int(home['score']),
                        leagueGame=event['competitions'][0]['conferenceCompetition'],
                        awayScore=int(away['score']), margin=margin, provider=provider)

        games = sorted(pool.map(game, events.items()), key=lambda g: (g['date'],g['id']))
        if not saved.keys() <= events.keys():
            raise ValueError('Incomplete scoreboard response: previously completed games missing')
        last_week = max(g['week'] for g in games)
        def poll(pair):
            week, poll_id = pair
            url = f'{CORE}/seasons/2026/types/2/weeks/{week}/rankings/{poll_id}'
            try:
                result = read(f'poll{week}-{poll_id}',url)
            except HTTPError as error:
                if error.code in (400,404):
                    return None
                raise
            if not result.get('ranks'):
                return None
            return dict(kind=result['type'], date=result['date'][:10], ranks={
                r['team']['$ref'].split('?')[0].split('/')[-1]:r['current'] for r in result['ranks']})
        polls = [p for p in pool.map(poll,[(w,k) for w in range(1,last_week+2) for k in (1,21)]) if p]

    market = market_snapshot(schedule, last_week, datetime.now(timezone.utc))
    payload = dict(teams=teams,games=games,polls=polls,market=market)
    (DATA / 'season.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path)
    collect(parser.parse_args().cache)
