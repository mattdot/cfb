"""Rebuild weekly ratings from the committed season inputs, without network access."""
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict
import json
import numpy as np
import ratings

ROOT = Path(__file__).resolve().parents[1]
BETA = 0.11295175807571445
MODEL = 'random-walk-hindsight-1'  # archived snapshots from another model are recomputed, not reused


def views(games, teams, market=None):
    """Current ratings and, per week, hindsight (ratings, top-25 reference, home field)."""
    fbs = {t for t in teams if teams[t]['fbs']}
    lined = [g for g in games if g['margin'] is not None]
    covered = len(lined)
    if market:
        lined.extend(market['quotes'])
        if len({g['id'] for g in lined}) != len(lined):
            raise ValueError('Duplicate game in market fit')
    if not lined:
        raise ValueError('At least one closing spread is required')
    snapshot_week = market['activeWeek'] if market else max(g['week'] for g in games)
    states = ratings.history(lined, teams, snapshot_week)
    # SOR judges each game in hindsight: both the opponent and the top-25 benchmark
    # as they were that week, re-estimated with every line through today.
    hindsight = {}
    for week, state in ratings.smooth(states).items():
        then, home_field = state.ratings()
        hindsight[week] = then, np.mean(sorted((then[t] for t in fbs), reverse=True)[:25]), home_field
    return states[snapshot_week].ratings(), hindsight, covered


def rank(games, teams, market=None):
    fbs = {t for t in teams if teams[t]['fbs']}
    (rating, _), hindsight, covered = views(games, teams, market)
    schedules = defaultdict(list)
    for g in games:
        home, away = g['home'], g['away']
        then, reference, home_field = hindsight[g['week']]
        for team, opponent, sign in [(home,away,1),(away,home,-1)]:
            if team not in fbs:
                continue
            venue = 0 if g['neutral'] else sign
            p = 1 / (1 + np.exp(-BETA * (reference-then[opponent]+venue*home_field)))
            won = sign * (g['homeScore']-g['awayScore']) > 0
            schedules[team].append((p, won))
    result = []
    for team, schedule in schedules.items():
        dist = np.array([1.0])
        wins = sum(won for _, won in schedule)
        for p, _ in schedule:
            dist = np.convolve(dist, [1-p, p])
        probability = min(1.0, float(sum(dist[wins:]))) if wins else 1.0
        result.append(dict(id=team, name=teams[team]['name'], wins=wins, losses=len(schedule)-wins, p=probability))
    result.sort(key=lambda r: (round(r['p'],14), r['name']))
    for i,row in enumerate(result):
        row['rank'] = result[i-1]['rank'] if i and round(row['p'],14)==round(result[i-1]['p'],14) else i+1
    return result, covered, {t: rating[t] for t in sorted(fbs)}


def team_pages(games, teams, market, rows, power, membership):
    """Each FBS team's schedule with closing lines beside hindsight lines, for team.html."""
    (current, home_field_now), hindsight, _ = views(games, teams, market)
    sor = {row['id']: row for row in rows}
    order = sorted(power, key=power.get, reverse=True)
    average = np.mean(list(power.values()))
    pages = {}
    for team in order:
        schedule = []
        entries = [(g, False) for g in games] + [(q, True) for q in (market['quotes'] if market else [])]
        for g, upcoming in entries:
            if team not in (g['home'], g['away']):
                continue
            sign = 1 if g['home'] == team else -1
            opponent = g['away'] if sign == 1 else g['home']
            then, reference, home_field = hindsight.get(g['week'], (current, None, home_field_now))
            venue = 0 if g['neutral'] else sign
            game = dict(week=g['week'], date=g.get('localDate') or g['kickoff'][:10], opp=opponent,
                        oppName=teams[opponent]['name'], site='neutral' if g['neutral'] else 'home' if sign == 1 else 'away',
                        line=None if g['margin'] is None else round(-sign * g['margin'], 1))
            if upcoming:
                game['upcoming'] = True
                game['projected'] = round(-(current[team] - current[opponent] + venue * home_field_now), 1)
            else:
                game['score'] = [g['homeScore'], g['awayScore']][::sign]
                game['hindsight'] = round(-(then[team] - then[opponent] + venue * home_field), 1)
                game['chance'] = round(float(1 / (1 + np.exp(-BETA * (reference - then[opponent] + venue * home_field)))), 4)
            schedule.append(game)
        schedule.sort(key=lambda x: (x['date'], x['week']))
        row = sor[team]
        pages[team] = dict(name=teams[team]['name'], conference=membership.get(team, ''), wins=row['wins'],
                           losses=row['losses'], sorRank=row['rank'], p=row['p'], vpiRank=order.index(team) + 1,
                           points=round(power[team] - average, 1), games=schedule)
    return pages


def build():
    season = json.loads((ROOT/'data/season.json').read_text())
    from conferences import summarize
    membership = json.loads((ROOT/'data/conferences-2026.json').read_text())
    archive = ROOT/'docs/archive'
    manifest = archive/'index.json'
    history = json.loads(manifest.read_text()) if manifest.exists() else []
    latest = {entry['week']:entry for entry in history}
    market = season.get('market')
    last_week = max(g['week'] for g in season['games'])
    output = []
    conference_weeks = {}
    through = max(g['localDate'] for g in season['games'])
    for week in sorted({g['week'] for g in season['games']}):
        games = [g for g in season['games'] if g['week']<=week]
        daily = market if week == last_week else None
        if not daily and week in latest:
            saved = json.loads((archive/latest[week]['file']).read_text())
            if saved['snapshot'].get('model') == MODEL and saved['snapshot']['games'] == len(games):
                output.append(saved['snapshot'])
                conference_weeks[week] = saved['conference']
                continue
        rows, covered, power = rank(games, season['teams'], daily)
        conference_weeks[week] = summarize(games, rows, power, membership, BETA)
        end = max(g['localDate'] for g in games)
        day = date.fromisoformat(end)
        # Pair a result week with the post-week polls through the next Tuesday.
        cutoff = min(through, (day+timedelta(days=(1-day.weekday())%7)).isoformat())
        if daily:
            cutoff = daily['asOf'][:10]
        releases = {}
        for kind in ('ap','cfp'):
            eligible = [p for p in season['polls'] if p['kind']==kind and p['date']<=cutoff]
            if eligible:
                poll = max(eligible,key=lambda p:p['date'])
                releases[kind] = poll['date']
                for row in rows:
                    row[kind] = poll['ranks'].get(row['id'])
        output.append(dict(week=week, through=end, games=len(games), lined=covered, model=MODEL, polls=releases, rows=rows))
        if daily:
            snapshot = output[-1]
            snapshot.update({k:v for k,v in daily.items() if k != 'quotes'})
            filename = daily['asOf'].replace(':','').replace('+0000','Z') + '.json'
            archive.mkdir(exist_ok=True)
            payload = dict(snapshot=snapshot, conference=conference_weeks[week], quotes=daily['quotes'])
            (archive/filename).write_text(json.dumps(payload,separators=(',',':')))
            entry = dict(week=week, asOf=daily['asOf'], file=filename)
            if entry not in history:
                history.append(entry)
            manifest.write_text(json.dumps(history,separators=(',',':')))
    final_games = [g for g in season['games'] if g['week'] <= last_week]
    final_rows, _, final_power = rank(final_games, season['teams'], market)
    pages = team_pages(final_games, season['teams'], market, final_rows, final_power, membership)
    stamp = dict(week=last_week, asOf=market['asOf'] if market else None, through=through)
    (ROOT/'docs/team-data.js').write_text('const teamSeason = '+json.dumps(dict(stamp, teams=pages),ensure_ascii=False,separators=(',',':'))+';\n')
    (ROOT/'docs/conference-data.js').write_text('const conferenceWeeks = '+json.dumps(conference_weeks,separators=(',',':'))+';\n')
    (ROOT/'docs/season.js').write_text('const season = '+json.dumps(output,ensure_ascii=False,separators=(',',':'))+';\n')


if __name__ == '__main__':
    build()
