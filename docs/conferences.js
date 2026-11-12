const $ = id => document.getElementById(id);
const params = new URLSearchParams(location.search);
const week = $('week'), league = $('league');
const initial = season.at(-1);
for (const s of season) week.add(new Option('Week '+s.week, s.week));
week.value = season.find(s => s.week === Number(params.get('week')))?.week ?? initial.week;
for (const name of Object.keys(conferenceWeeks[initial.week].groups)) league.add(new Option(name));
league.value = [...league.options].some(x=>x.value===params.get('conference')) ? params.get('conference') : 'Big Ten';
const comparisonSort = {key:'median', direction:-1};
const teamSort = {key:'powerRank', direction:1};
let focused = null;
const fmt = n => (n > 0 ? '+' : '') + n.toFixed(1);
const rec = (w,l) => w+'–'+l;
function sum(items, key) {return items.reduce((total,x)=>total+x[key],0);}
function table(id, columns, data, sort, onSelect) {
  const t=$(id), header=t.tHead, body=t.tBodies[0];
  header.replaceChildren(); body.replaceChildren();
  const head=header.insertRow();
  for(const [key,label,,direction] of columns){
    const h=document.createElement('th'); head.append(h); h.scope='col';
    const b=document.createElement('button');h.append(b);
    b.textContent=label+(sort.key===key?(sort.direction>0?' ↑':' ↓'):'');
    if(sort.key===key)h.setAttribute('aria-sort',sort.direction>0?'ascending':'descending');
    b.onclick=()=>{sort.direction=sort.key===key?-sort.direction:direction;sort.key=key;render();};
  }
  const value=x=>x[sort.key];
  data.sort((a,b)=>{
    const x=value(a),y=value(b);
    if(x==null||y==null)return Number(x==null)-Number(y==null);
    return sort.direction*(typeof x==='string'?x.localeCompare(y):x-y)||a.name.localeCompare(b.name);
  });
  for(const r of data){
    const tr=body.insertRow();
    if(r.selected)tr.className='selected';
    if(r.id)tr.id='team-'+r.id;
    for(const [key,,display] of columns){
      const cell=tr.insertCell(), text=display?display(r):r[key]??'—';
      if(key==='name' && onSelect){
        const b=document.createElement('button');b.textContent=text;b.onclick=()=>onSelect(r);cell.append(b);
      }else cell.textContent=text;
    }
  }
}
function choose(name,id=null){
  league.value=name;focused=id;render();
  const el=id?$('team-'+id):$('detail');el?.scrollIntoView({block:'center'});
}
function chart(teams, groups) {
  const container=$('chart');container.replaceChildren();
  const points=Object.values(teams).map(t=>t.points);
  const bound=Math.max(10,Math.ceil(Math.max(...points.map(Math.abs))/5)*5);
  const percent=x=>50+50*x/bound;
  const axis=document.createElement('div');axis.className='chartrow';axis.innerHTML='<b>Neutral field</b><div class="axis"><span>−'+bound+'</span><span>0</span><span>+'+bound+' pts</span></div>';container.append(axis);
  for(const g of groups){
    const row=document.createElement('div');row.className='chartrow';
    const name=document.createElement('b');name.textContent=g.name;
    const track=document.createElement('div');track.className='track';
    row.append(name,track);container.append(row);
    const median=document.createElement('span');median.className='median';median.style.left=percent(g.median)+'%';track.append(median);
    const lanes=[];
    for(const team of Object.values(teams).filter(t=>t.conference===g.name).sort((a,b)=>a.points-b.points)){
      const x=percent(team.points);
      let lane=lanes.findIndex(last=>x-last>=100*14/Math.max(1,track.clientWidth));
      if(lane<0)lane=lanes.length;
      lanes[lane]=x;
      const dot=document.createElement('button');dot.className='dot';dot.style.left=x+'%';dot.style.top=(8+14*lane)+'px';
      dot.title=team.name+' · '+fmt(team.points)+' pts';dot.setAttribute('aria-label',dot.title);
      dot.onclick=()=>choose(g.name,team.id);track.append(dot);
    }
    track.style.height=(lanes.length*14+3)+'px';
  }
}
function render(){
  const s=season.find(x=>x.week===Number(week.value)), c=conferenceWeeks[s.week];
  const url=new URL(location.href);url.searchParams.set('week',week.value);url.searchParams.set('conference',league.value);history.replaceState(null,'',url);
  $('rankings').href='./?week='+week.value;$('cutoff').textContent='Through '+s.through;
  const teams=s.rows.map(r=>({...r,...c.teams[r.id],selected:r.id===focused}));
  const groups=Object.entries(c.groups).map(([name,g])=>{
    const opponents=Object.values(g.opponents);
    return {...g,name,selected:name===league.value,w:sum(opponents,'w'),l:sum(opponents,'l'),expected:sum(opponents,'expected'),diff:sum(opponents,'actual')-sum(opponents,'expected')};
  });
  table('comparison',[
    ['name','Conference',null,1],['median','Median pts',r=>fmt(r.median),-1],['top','Top 3 pts',r=>fmt(r.top),-1],['top25','Top 25 SOR',null,-1],['w','Outside W–L',r=>rec(r.w,r.l),-1],['expected','Exp. wins',r=>r.expected.toFixed(1),-1],['diff','Wins ±',r=>fmt(r.diff),-1]
  ],groups,comparisonSort,r=>choose(r.name));
  chart(teams,groups);
  const members=teams.filter(t=>t.conference===league.value);
  $('leagueTitle').textContent=league.value;
  $('teamSummary').textContent=members.length+' teams · AP '+(s.polls.ap??'unreleased')+' · CFP '+(s.polls.cfp??'unreleased');
  table('members',[
    ['name','Team',null,1],['wins','Overall',r=>rec(r.wins,r.losses),-1],['cw','Conf.',r=>league.value==='Independents'?'—':rec(r.cw,r.cl),-1],['points','Power pts',r=>fmt(r.points),-1],['powerRank','Power rank',null,1],['rank','Vegas SOR',null,1],['ap','AP',null,1],['cfp','CFP',null,1]
  ],members,teamSort);
  const body=$('opponents').tBodies[0];body.replaceChildren();
  const entries=Object.entries(c.groups[league.value].opponents).sort(([a],[b])=>Number(a==='FCS')-Number(b==='FCS')||a.localeCompare(b));
  for(const [name,r] of entries){
    const tr=body.insertRow();
    for(const v of [name,r.w+r.l,rec(r.w,r.l),r.lined,r.expected.toFixed(1),fmt(r.actual-r.expected)])tr.insertCell().textContent=v;
  }
  $('note').textContent=entries.length?'':'No outside games completed through this week.';
}
week.onchange=league.onchange=()=>{focused=null;render();};
let lastWidth=innerWidth;
window.addEventListener('resize',()=>{if(innerWidth!==lastWidth){lastWidth=innerWidth;render();}});
render();
