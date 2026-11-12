const weeks = document.querySelector('#week');
const search = document.querySelector('#search');
const requested = Number(new URLSearchParams(location.search).get('week'));
for (const snapshot of season) {
  weeks.add(new Option('Week ' + snapshot.week, snapshot.week));
}
weeks.value = season.find(s => s.week === requested)?.week ?? season.at(-1).week;
function render() {
  const s = season.find(item => item.week === Number(weeks.value));
  const matches = s.rows.filter(r => r.name.toLowerCase().includes(search.value.trim().toLowerCase()));
  document.querySelector('#summary').textContent =
    'Through ' + s.through + ' · ' + s.rows.length + ' teams · ' + s.games + ' games. Lower chance means a stronger record.';
  const body = document.querySelector('#rows');
  body.replaceChildren();
  for (const row of matches) {
    const tr = body.insertRow();
    for (const value of [row.rank, row.name, row.wins+'–'+row.losses, (100*row.p).toFixed(2)+'%', row.ap ?? '—', row.cfp ?? '—']) {
      tr.insertCell().textContent = value;
    }
  }
  document.querySelector('#empty').hidden = matches.length > 0;
  document.querySelector('#polls').textContent = 'Reference polls: AP ' + (s.polls.ap ?? 'unreleased') +
    ' · CFP ' + (s.polls.cfp ?? 'unreleased') + '. A dash means unranked or no poll released.';
}
weeks.onchange = () => {
  const url = new URL(location.href);
  url.searchParams.set('week', weeks.value);
  history.replaceState(null, '', url);
  render();
};
search.oninput = render;
render();
