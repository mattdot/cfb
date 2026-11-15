const weeks = document.querySelector('#week');
const search = document.querySelector('#search');
const conference = document.querySelector('#conference');
const params = new URLSearchParams(location.search);
for (const snapshot of season) {
  weeks.add(new Option('Week ' + snapshot.week, snapshot.week));
}
weeks.value = season.find(s => s.week === Number(params.get('week')))?.week ?? season.at(-1).week;

function setConferenceOptions(selected) {
  if (!conference) return;
  const names = Object.keys(conferenceWeeks[weeks.value].groups).sort();
  conference.replaceChildren(new Option('All conferences', ''));
  for (const name of names) conference.add(new Option(name, name));
  conference.value = names.includes(selected) ? selected : '';
}

function render() {
  const s = season.find(item => item.week === Number(weeks.value));
  const teams = conferenceWeeks[s.week].teams;
  const previous = previousRanks(s.week);
  const priorPower = new Map(Object.entries(conferenceWeeks[s.week - 1]?.teams ?? {})
    .map(([id, team]) => [id, team.powerRank]));
  const query = search.value.trim().toLowerCase();
  const matches = s.rows.filter(row => row.name.toLowerCase().includes(query) &&
    (!conference?.value || teams[row.id].conference === conference.value));
  if (conference) matches.sort((a, b) => teams[a.id].powerRank - teams[b.id].powerRank);

  document.querySelector('#summary').textContent = 'Through ' + s.through + ' · ' +
    (conference ? matches.length : s.rows.length) + ' teams · ' + s.games + ' games nationally.' +
    (conference ? ' Ranks are national.' : ' Lower chance means a stronger record.');
  const body = document.querySelector('#rows');
  body.replaceChildren();
  for (const row of matches) {
    const power = teams[row.id];
    const points = (power.points > 0 ? '+' : '') + power.points.toFixed(1);
    const record = row.wins + '–' + row.losses;
    const tr = body.insertRow();
    if (conference) {
      tr.insertCell().append(rankWithMovement({id: row.id, rank: power.powerRank}, priorPower));
    } else {
      tr.insertCell().append(rankWithMovement(row, previous));
    }
    const values = conference
      ? [row.name, power.conference, points, record, row.rank]
      : [row.name, record, (100 * row.p).toFixed(2) + '%', power.powerRank, points, row.ap ?? '—', row.cfp ?? '—'];
    for (const value of values) tr.insertCell().textContent = value;
  }
  document.querySelector('#empty').hidden = matches.length > 0;
  if (!conference) {
    document.querySelector('#polls').textContent = 'Reference polls: AP ' + (s.polls.ap ?? 'unreleased') +
      ' · CFP ' + (s.polls.cfp ?? 'unreleased') + '. A dash means unranked or no poll released.';
  }
  const other = document.querySelector(conference ? '#sor-link' : '#vpi-link');
  other.href = (conference ? './' : 'vpi.html') + '?week=' + s.week;
  document.querySelector('a[href^="conferences.html"]').href = 'conferences.html?week=' + s.week +
    (conference?.value ? '&conference=' + encodeURIComponent(conference.value) : '');
}

function changeSelection() {
  const url = new URL(location.href);
  url.searchParams.set('week', weeks.value);
  if (conference?.value) url.searchParams.set('conference', conference.value);
  else url.searchParams.delete('conference');
  history.replaceState(null, '', url);
  render();
}

weeks.onchange = () => {
  setConferenceOptions(conference?.value);
  changeSelection();
};
if (conference) conference.onchange = changeSelection;
search.oninput = render;
setConferenceOptions(params.get('conference'));
render();
