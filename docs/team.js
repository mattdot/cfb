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

// Rank-by-week chart: SOR and VPI rank share one axis (rank among FBS teams), 1 at the top.
const SERIES = [{key: 'sor', label: 'SOR', color: '#2a78d6'}, {key: 'vpi', label: 'VPI', color: '#eb6834'}];
const SVG = 'http://www.w3.org/2000/svg';
let trendIndex = null;

function svg(tag, attrs, parent) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  parent?.append(node);
  return node;
}

function niceTicks(max) {
  const step = [5, 10, 20, 25, 50].find(s => max / s <= 5) ?? 50;
  const top = Math.max(step, Math.ceil(max / step) * step);
  const ticks = [1];
  for (let t = step; t <= top; t += step) ticks.push(t);
  return {top, ticks};
}

function renderTrend() {
  const team = teams[select.value];
  const history = team.history ?? [];
  const plot = document.querySelector('#trend-plot');
  const tip = document.querySelector('#trend-tip');
  plot.replaceChildren();
  tip.hidden = true;
  const rows = document.querySelector('#trend-rows');
  rows.replaceChildren();
  for (const h of history) {
    const tr = rows.insertRow();
    for (const value of [h.week, h.sor ?? '—', h.vpi ?? '—']) tr.insertCell().textContent = value;
  }
  if (history.length < 2) {
    plot.textContent = 'Not enough weeks yet.';
    return;
  }
  const width = Math.max(300, plot.clientWidth);
  const height = 240;
  const m = {left: 40, right: 64, top: 14, bottom: 30};
  const ranks = history.flatMap(h => [h.sor, h.vpi]).filter(v => v != null);
  const {top, ticks} = niceTicks(Math.max(...ranks));
  const x = i => m.left + i * (width - m.left - m.right) / (history.length - 1);
  const y = r => m.top + (r - 1) * (height - m.top - m.bottom) / (top - 1);
  const root = svg('svg', {width, height, viewBox: `0 0 ${width} ${height}`, role: 'img', tabindex: 0,
    'aria-label': `${team.name}: SOR rank ${history.at(-1).sor ?? 'none'} and VPI rank ${history.at(-1).vpi ?? 'none'} after week ${history.at(-1).week}. Use arrow keys to read each week.`}, plot);
  for (const t of ticks) {
    svg('line', {x1: m.left, x2: width - m.right, y1: y(t), y2: y(t), class: 'grid'}, root);
    svg('text', {x: m.left - 8, y: y(t) + 4, 'text-anchor': 'end', class: 'tick'}, root).textContent = t;
  }
  // Week labels: 'Wk N' when there's room, bare numbers when tight, thinned so they never touch.
  const spacing = (width - m.left - m.right) / (history.length - 1);
  const short = spacing < 44;
  const every = Math.ceil((short ? 22 : 44) / spacing);
  history.forEach((h, i) => {
    if ((history.length - 1 - i) % every === 0)
      svg('text', {x: x(i), y: height - 8, 'text-anchor': 'middle', class: 'tick'}, root).textContent = (short ? '' : 'Wk ') + h.week;
  });
  if (short) svg('text', {x: m.left - 8, y: height - 8, 'text-anchor': 'end', class: 'tick'}, root).textContent = 'Wk';
  const cross = svg('line', {y1: m.top, y2: height - m.bottom, class: 'cross', visibility: 'hidden'}, root);
  for (const s of SERIES) {
    let d = '', pen = false;
    history.forEach((h, i) => {
      if (h[s.key] == null) { pen = false; return; }
      d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ',' + y(h[s.key]).toFixed(1);
      pen = true;
    });
    svg('path', {d, class: 'line', stroke: s.color}, root);
    history.forEach((h, i) => {
      if (h[s.key] != null) svg('circle', {cx: x(i), cy: y(h[s.key]), r: 4, fill: s.color, class: 'dot'}, root);
    });
  }
  // Direct end labels unless the two series end too close together; the legend always names them.
  const last = history.at(-1);
  const ends = SERIES.filter(s => last[s.key] != null).map(s => ({s, py: y(last[s.key])}));
  if (ends.length < 2 || Math.abs(ends[0].py - ends[1].py) >= 14) {
    for (const {s, py} of ends)
      svg('text', {x: x(history.length - 1) + 10, y: py + 4, class: 'end'}, root).textContent = s.label + ' ' + last[s.key];
  }
  const show = i => {
    trendIndex = i;
    const h = history[i];
    cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('visibility', 'visible');
    tip.replaceChildren();
    const head = document.createElement('div');
    head.className = 'tip-head';
    head.textContent = 'Week ' + h.week;
    tip.append(head);
    for (const s of SERIES) {
      const row = document.createElement('div');
      const key = document.createElement('i');
      key.className = 'key ' + s.key;
      const value = document.createElement('strong');
      value.textContent = h[s.key] == null ? '—' : '#' + h[s.key];
      row.append(key, value, ' ' + s.label);
      tip.append(row);
    }
    tip.hidden = false;
    const left = x(i) + 12 + tip.offsetWidth > width ? x(i) - 12 - tip.offsetWidth : x(i) + 12;
    tip.style.left = left + 'px';
    tip.style.top = plot.offsetTop + m.top + 'px';
  };
  const hide = () => { cross.setAttribute('visibility', 'hidden'); tip.hidden = true; trendIndex = null; };
  const hit = svg('rect', {x: m.left - 12, y: 0, width: width - m.left - m.right + 24, height, fill: 'transparent'}, root);
  const nearest = event => {
    const box = root.getBoundingClientRect();
    const px = event.clientX - box.left;
    return Math.max(0, Math.min(history.length - 1, Math.round((px - m.left) / ((width - m.left - m.right) / (history.length - 1)))));
  };
  hit.addEventListener('pointermove', e => show(nearest(e)));
  hit.addEventListener('pointerdown', e => show(nearest(e)));
  root.addEventListener('pointerleave', hide);
  root.addEventListener('blur', hide);
  root.addEventListener('focus', () => show(history.length - 1));
  root.addEventListener('keydown', e => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    const i = trendIndex ?? history.length - 1;
    show(Math.max(0, Math.min(history.length - 1, i + (e.key === 'ArrowRight' ? 1 : -1))));
  });
}

const baseRender = render;
select.onchange = () => { baseRender(); renderTrend(); };
let resizeTimer;
addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderTrend, 150); });
renderTrend();
