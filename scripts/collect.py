"""Collect completed 2026 regular-season games and dated poll releases."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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


def closing_margin(document):
    for item in sorted(document['items'], key=lambda x: x['provider']['id'] != '100'):
        close = item.get('homeTeamOdds', {}).get('close', {}).get('pointSpread', {})
        if close.get('american') is not None:
            return -float(close['american']), item['provider']['name']
    return None, None


def collect(cache):
    def read(key, url):
        file = cache / key if cache else None
        return json.loads(file.read_text()) if file and file.exists() else fetch(url)

    def scoreboard(week):
        return read(f'w{week}', f'{SITE}/scoreboard?dates=2026&seasontype=2&week={week}&groups=80&limit=200')

    old = json.loads((DATA / 'season.json').read_text()) if (DATA / 'season.json').exists() else {}
    saved = {g['id']: g for g in old.get('games', [])}
    teams, events = {}, {}
    with ThreadPoolExecutor(8) as pool:
        for board in pool.map(scoreboard, range(1, 17)):
            for event in board['events']:
                if event['season']['year'] != 2026 or event['season']['type'] != 2:
                    continue
                match = event['competitions'][0]
                sides = {entry['homeAway']: entry for entry in match['competitors']}
                if not all(k in sides for k in ('home','away')):
                    continue
                for side in sides.values():
                    t = side['team']
                    teams[t['id']] = dict(name=t['location'], full=t['displayName'], fbs=t.get('conferenceId') in FBS)
                if event['status']['type']['completed'] and any(teams[s['id']]['fbs'] for s in sides.values()):
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

    payload = dict(teams=teams,games=games,polls=polls)
    (DATA / 'season.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path)
    collect(parser.parse_args().cache)
