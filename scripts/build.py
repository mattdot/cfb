"""Rebuild weekly ratings from the committed season inputs, without network access."""
from datetime import date, timedelta
from pathlib import Path
from collections import defaultdict
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HALF_LIFE_WEEKS = 2
BETA = 0.11295175807571445


def rank(games, teams, market=None):
    ids = sorted(teams)
    index = {team: i for i, team in enumerate(ids)}
    fbs = [t for t in ids if teams[t]['fbs']]
    lined = [g for g in games if g['margin'] is not None]
    covered = len(lined)
    if market:
        lined.extend(market['quotes'])
        if len({g['id'] for g in lined}) != len(lined):
            raise ValueError('Duplicate game in market fit')
    if not lined:
        raise ValueError('At least one closing spread is required')
    snapshot_week = market['activeWeek'] if market else max(g['week'] for g in games)
    design = np.zeros((len(lined), len(ids) + 2))
    weight, target = [], []
    for i, g in enumerate(lined):
        h, a = g['home'], g['away']
        design[i,index[h]] = 1
        design[i,index[a]] = -1
        design[i,-2] = int(h not in fbs) - int(a not in fbs)
        design[i,-1] = int(not g['neutral'])
        age_weeks = snapshot_week - g['week']
        weight.append(2 ** (-age_weeks / HALF_LIFE_WEEKS))
        target.append(g['margin'])
    prior = np.zeros(len(ids)+2)
    prior[-1] = 2.5
    penalty = np.array([0.1 if t in fbs else 2 for t in ids] + [0.001,1])
    weighted = design.T * weight
    coef = np.linalg.solve(weighted @ design + np.diag(penalty), weighted @ target + penalty * prior)
    rating = {t: coef[index[t]] + (0 if t in fbs else coef[-2]) for t in ids}
    reference = np.mean(sorted((rating[t] for t in fbs), reverse=True)[:25])
    schedules = defaultdict(list)
    for g in games:
        home, away = g['home'], g['away']
        for team, opponent, sign in [(home,away,1),(away,home,-1)]:
            if team not in fbs:
                continue
            venue = 0 if g['neutral'] else sign
            p = 1 / (1 + np.exp(-BETA * (reference-rating[opponent]+venue*coef[-1])))
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
    return result, covered, {t: rating[t] for t in fbs}


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
            if saved['snapshot']['games'] == len(games):
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
        output.append(dict(week=week, through=end, games=len(games), lined=covered, polls=releases, rows=rows))
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
    (ROOT/'docs/conference-data.js').write_text('const conferenceWeeks = '+json.dumps(conference_weeks,separators=(',',':'))+';\n')
    (ROOT/'docs/season.js').write_text('const season = '+json.dumps(output,ensure_ascii=False,separators=(',',':'))+';\n')


if __name__ == '__main__':
    build()
