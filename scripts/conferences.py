"""Summarize the same weekly market fit used for SOR."""
from collections import defaultdict
from math import exp
from statistics import mean, median


def summarize(games, rows, power, membership, slope):
    average = mean(power.values())
    ordered = sorted(power, key=power.get, reverse=True)
    teams = {team: dict(points=round(power[team]-average, 4), powerRank=i,
                        conference=membership[team], cw=0, cl=0)
             for i, team in enumerate(ordered, 1)}
    groups = defaultdict(lambda: defaultdict(lambda: dict(w=0, l=0, lined=0, actual=0, expected=0.0)))
    for game in games:
        home, away = game['home'], game['away']
        home_won = game['homeScore'] > game['awayScore']
        for team, opponent, sign in ((home,away,1),(away,home,-1)):
            if team not in teams:
                continue
            conf = membership[team]
            other = membership.get(opponent,'FCS')
            won = home_won if sign==1 else not home_won
            if game['leagueGame'] and conf==other and conf!='Independents':
                teams[team]['cw' if won else 'cl'] += 1
            elif conf!=other or conf=='Independents':
                stats = groups[conf][other]
                stats['w' if won else 'l'] += 1
                if game['margin'] is not None:
                    stats['lined'] += 1
                    stats['actual'] += int(won)
                    stats['expected'] += 1/(1+exp(-slope*sign*game['margin']))
    summaries = {}
    for conf in sorted(set(membership.values())):
        ratings = sorted((t['points'] for t in teams.values() if t['conference']==conf), reverse=True)
        summaries[conf] = dict(median=median(ratings), top=mean(ratings[:3]),
                               top25=sum(r['rank']<=25 and membership[r['id']]==conf for r in rows),
                               opponents=groups[conf])
    return dict(teams=teams, groups=summaries)
