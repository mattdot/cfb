const weeks = document.querySelector('#week');
const search = document.querySelector('#search');
const conference = document.querySelector('#conference');
const params = new URLSearchParams(location.search);
for (const snapshot of season) {
  weeks.add(new Option('Week ' + snapshot.week, snapshot.week));
}
weeks.value = season.find(s => s.week === Number(params.get('week')))?.week ?? season.at(-1).week;

const edition = document.querySelector('#edition');
let historyEntries = [];
let archived = null;
let selectionRequest = 0;

function setEditions() {
  const entries = historyEntries.filter(entry => entry.week === Number(weeks.value)).reverse();
  edition.replaceChildren(new Option('Latest for week', ''));
  const formatter = new Intl.DateTimeFormat('en-US', {timeZone:'America/Los_Angeles',
    month:'short', day:'numeric', hour:'numeric', minute:'2-digit', timeZoneName:'short'});
  for (const entry of entries) edition.add(new Option(formatter.format(new Date(entry.asOf)), entry.file));
  document.querySelector('#edition-label').hidden = entries.length === 0;
}

async function loadEdition() {
  const request = ++selectionRequest;
  archived = null;
  const entry = historyEntries.find(e => e.file === edition.value && e.week === Number(weeks.value));
  if (entry) {
    try {
      const response = await fetch('archive/' + entry.file);
      if (!response.ok) throw Error('Archive unavailable');
      const data = await response.json();
      if (request !== selectionRequest) return;
      archived = data;
    } catch {
      if (request === selectionRequest) {
        document.querySelector('#summary').textContent = 'Archived update could not be loaded. Select another update to retry.';
        document.querySelector('#rows').replaceChildren();
      }
      return;
    }
  }
  changeSelection();
}

function setConferenceOptions(selected) {
  if (!conference) return;
  const names = Object.keys(conferenceWeeks[weeks.value].groups).sort();
  conference.replaceChildren(new Option('All conferences', ''));
  for (const name of names) conference.add(new Option(name, name));
  conference.value = names.includes(selected) ? selected : '';
}

function render() {
  const s = archived?.snapshot ?? season.find(item => item.week === Number(weeks.value));
  const teams = (archived?.conference ?? conferenceWeeks[s.week]).teams;
  const previous = previousRanks(s.week);
  const priorPower = new Map(Object.entries(conferenceWeeks[precedingSnapshot(s.week)?.week]?.teams ?? {})
    .map(([id, team]) => [id, team.powerRank]));
  const query = search.value.trim().toLowerCase();
  const matches = s.rows.filter(row => row.name.toLowerCase().includes(query) &&
    (!conference?.value || teams[row.id].conference === conference.value));
  if (conference) matches.sort((a, b) => teams[a.id].powerRank - teams[b.id].powerRank);

  document.querySelector('#summary').textContent = updateSummary(s) + ' · ' + matches.length + ' teams';
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
      : [row.name, record, (100 * row.p).toFixed(2) + '%', power.powerRank, row.ap ?? '—', row.cfp ?? '—'];
    for (const value of values) tr.insertCell().textContent = value;
  }
  document.querySelector('#empty').hidden = matches.length > 0;
  if (!conference) {
    document.querySelector('#polls').textContent = 'Reference polls: AP ' + (s.polls.ap ?? 'unreleased') +
      ' · CFP ' + (s.polls.cfp ?? 'unreleased') + '. A dash means unranked or no poll released.';
  }
  const other = document.querySelector(conference ? '#sor-link' : '#vpi-link');
  other.href = (conference ? './' : 'vpi.html') + '?week=' + s.week;
  if (archived) other.href += '&asof=' + encodeURIComponent(edition.value);
  document.querySelector('a[href^="conferences.html"]').href = 'conferences.html?week=' + s.week +
    (conference?.value ? '&conference=' + encodeURIComponent(conference.value) : '');
}

function changeSelection() {
  const url = new URL(location.href);
  url.searchParams.set('week', weeks.value);
  if (edition.value) url.searchParams.set('asof', edition.value);
  else url.searchParams.delete('asof');
  if (conference?.value) url.searchParams.set('conference', conference.value);
  else url.searchParams.delete('conference');
  history.replaceState(null, '', url);
  render();
}

weeks.onchange = () => {
  ++selectionRequest;
  archived = null;
  setEditions();
  setConferenceOptions(conference?.value);
  changeSelection();
};
if (conference) conference.onchange = changeSelection;
search.oninput = render;
setConferenceOptions(params.get('conference'));
render();

edition.onchange = loadEdition;
if (season.some(s => s.asOf)) {
  fetch('archive/index.json').then(response => response.json()).then(entries => {
    historyEntries = entries;
    setEditions();
    if (entries.some(e => e.week === Number(weeks.value) && e.file === params.get('asof'))) {
      edition.value = params.get('asof');
      loadEdition();
    }
  }).catch(() => { document.querySelector('#edition-label').hidden = true; });
}
