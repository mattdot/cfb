function previousRanks(week) {
  const previous = season.find(snapshot => snapshot.week === week - 1);
  return new Map(previous?.rows.map(team => [team.id, team.rank]));
}

function rankWithMovement(team, previous) {
  const rank = document.createElement('span');
  rank.className = 'sor-rank';
  rank.textContent = team.rank;
  const prior = previous.get(team.id);
  if (prior == null) {
    rank.title = 'No prior-week rank';
    return rank;
  }

  const change = prior - team.rank;
  const movement = document.createElement('small');
  const direction = change > 0 ? 'up' : change < 0 ? 'down' : 'unchanged';
  movement.className = 'rank-change ' + direction;
  movement.title = change ? direction + ' ' + Math.abs(change) + ' from #' + prior + ' last week' : 'Unchanged from last week';
  movement.setAttribute('role', 'img');
  movement.setAttribute('aria-label', movement.title);
  movement.textContent = change ? (change > 0 ? '▲' : '▼') + Math.abs(change) : '–';
  rank.append(movement);
  return rank;
}
