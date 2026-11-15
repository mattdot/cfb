const select = document.querySelector('#team');
const teams = teamSeason.teams;
const ids = Object.keys(teams).sort((a, b) => teams[a].name.localeCompare(teams[b].name));
for (const id of ids) select.add(new Option(teams[id].name, id));
const bySor = Object.keys(teams).sort((a, b) => teams[a].sorRank - teams[b].sorRank);
const requested = new URLSearchParams(location.search).get('team');
select.value = teams[requested] ? requested : bySor[0];

const spread = value => value == null ? '—' : value === 0 ? 'PK' : (value > 0 ? '+' : '−') + Math.abs(value).toFixed(1);
const day = new Intl.DateTimeFormat('en-US', {month: 'short', day: 'numeric', timeZone: 'UTC'});

if (teamSeason.asOf) {
  const updated = new Intl.DateTimeFormat('en-US', {timeZone: 'America/Los_Angeles', month: 'short', day: 'numeric',
    hour: 'numeric', minute: '2-digit', timeZoneName: 'short'}).format(new Date(teamSeason.asOf));
  document.querySelector('#stamp').textContent = 'Updated ' + updated + ' · results through ' + teamSeason.through;
} else {
  document.querySelector('#stamp').textContent = 'Results through ' + teamSeason.through;
}

function opponentCell(game) {
  const cell = document.createElement('td');
  const prefix = game.site === 'away' ? 'at ' : game.site === 'neutral' ? 'vs ' : '';
  cell.append(prefix);
  if (teams[game.opp]) {
    const link = document.createElement('a');
    link.href = 'team.html?team=' + game.opp;
    link.textContent = game.oppName;
    cell.append(link);
  } else {
    cell.append(game.oppName);
  }
  return cell;
}

function render() {
  const team = teams[select.value];
  document.title = team.name + ' schedule · Vegas SOR';
  document.querySelector('#name').textContent = team.name;
  const points = (team.points > 0 ? '+' : '') + team.points.toFixed(1);
  document.querySelector('#summary').textContent = team.wins + '–' + team.losses + (team.conference ? ' · ' + team.conference : '') +
    ' · SOR #' + team.sorRank + ' (' + (100 * team.p).toFixed(2) + '% chance) · VPI #' + team.vpiRank + ' (' + points + ' pts)';
  const body = document.querySelector('#games');
  body.replaceChildren();
  for (const game of team.games) {
    const tr = body.insertRow();
    if (game.upcoming) tr.className = 'upcoming';
    tr.insertCell().textContent = game.week;
    tr.append(opponentCell(game));
    tr.insertCell().textContent = day.format(new Date(game.date + 'T00:00:00Z'));
    let result = 'Upcoming';
    if (!game.upcoming) {
      const [mine, theirs] = game.score;
      result = (mine > theirs ? 'W ' : 'L ') + mine + '–' + theirs;
    }
    tr.insertCell().textContent = result;
    tr.insertCell().textContent = spread(game.line);
    const hindsight = tr.insertCell();
    if (game.upcoming) {
      hindsight.textContent = 'VPI ' + spread(game.projected);
      hindsight.title = 'Projection from current VPI ratings';
    } else {
      hindsight.textContent = spread(game.hindsight);
      if (game.line != null) {
        const shift = game.hindsight - game.line;
        hindsight.title = Math.abs(shift) < 0.05 ? 'Same as the closing line'
          : 'Hindsight moves the line ' + Math.abs(shift).toFixed(1) + ' points ' + (shift < 0 ? 'toward' : 'away from') + ' ' + team.name;
        if (Math.abs(shift) >= 3) hindsight.className = 'shifted';
      }
    }
    tr.insertCell().textContent = game.upcoming ? '—' : Math.round(100 * game.chance) + '%';
  }
  const url = new URL(location.href);
  url.searchParams.set('team', select.value);
  history.replaceState(null, '', url);
}

select.onchange = render;
render();
