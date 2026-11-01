/* Exercise the inline outage dashboard in Node without network or browser packages. */
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const html=fs.readFileSync('site/index.html','utf8');
const source=[...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)]
  .filter(m=>!/\bsrc\s*=/.test(m[1]))[0]?.[2];
assert.ok(source,'Expected one embedded dashboard script');

class NodeStub {
  constructor(id) {
    this.id=id;this.dataset={};this.style={
      setProperty(){},removeProperty(){}};
    this.hidden=false;this.open=false;this.innerHTML='';this.textContent='';
    this.attributes=new Map();this.events={};this.parentElement=null;
    this.scrollHeight=0;this.clientHeight=0;this.scrollTop=0;
    const state=new Set();
    this.classList={
      add(...a){a.forEach(x=>state.add(x));},remove(...a){a.forEach(x=>state.delete(x));},
      toggle(x,force){if(force===false || (force===undefined&&state.has(x))){state.delete(x);return false;}state.add(x);return true;},
      contains:x=>state.has(x)};
  }
  addEventListener(ev, fn){this.events[ev]=fn;}
  setAttribute(k,v){this.attributes.set(k,String(v));}
  getAttribute(k){return this.attributes.get(k)||null;}
  removeAttribute(k){this.attributes.delete(k);}
  querySelector(){return null;}
  querySelectorAll(){return [];}
  closest(){return this;}
  focus(){}
  getBoundingClientRect(){return {width:0,height:0,left:0,top:0,right:0,bottom:0};}
}

function makePayload(today) {
  const day=(offset=0)=>{const d=new Date(today+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+offset);return d.toISOString().slice(0,10);};
  const todayIso=day(),tomorrow=day(1);
  const normal={status:'normal',date:todayIso,outages:[['07:30','10:00'],['18:00','20:00']],
    sources:['КолиСвітло','КолиБуде'],source_reports:{
      'КолиСвітло':{status:'match',outages:[['07:30','10:00'],['18:00','20:00']]},
      'КолиБуде':{status:'match',outages:[['07:30','10:00'],['18:00','20:00']]}}};
  const unknown={status:'unknown',date:tomorrow,outages:[],sources:[],source_reports:{}};
  const locations={};
  for(const [key,group] of Object.entries({dacha:'3.1',home:'4.1',solovky:'4.1',naumenky:'10.1'})) {
    locations[key]={name:key,group,days:{[todayIso]:normal,[tomorrow]:unknown},logs:[],emergency:null};
  }
  locations.home.emergency={level:'active',source_checked:true,url:'https://t.me/dtek_ua/12345',
    published_at:todayIso+'T08:00:00+02:00'};
  return {updated_at:new Date().toISOString(),today_date:todayIso,tomorrow_date:tomorrow,
    days:locations.dacha.days,logs:[],locations,source_health:{issues:[]}};
}
function runDashboard() {
  const nodes=new Map(),docEvents={},windowEvents={},storage=new Map(),tabs=[],siteViews=[],locations=[];
  const node=id=>{if(!nodes.has(id))nodes.set(id,new NodeStub(id));return nodes.get(id);};
  ['today','tomorrow'].forEach(tab=>{const e=new NodeStub('tab-'+tab);e.dataset.tab=tab;tabs.push(e);});
  ['schedule','statistics'].forEach(view=>{const e=new NodeStub('view-'+view);e.dataset.siteView=view;siteViews.push(e);});
  ['dacha','home','solovky','naumenky'].forEach(key=>{
    const e=new NodeStub('location-'+key);
    e.dataset.location=key;
    e.querySelector=sel=>sel==='.location-group-hint'?node('hint-'+key):null;
    locations.push(e);
  });
  node('viewMenu').hidden=true;
  node('seasonPanel').hidden=true;
  node('marker').querySelector=()=>null;
  const document={
    getElementById:node,body:node('body'),documentElement:node('documentElement'),
    addEventListener:(k,fn)=>{docEvents[k]=fn;},
    querySelector:sel=>{
      if(sel==='[data-tab="tomorrow"]')return tabs[1];
      if(sel==='#display .graph')return null;
      if(sel==='main > header')return node('header');
      return null;
    },
    querySelectorAll:sel=>{
      if(sel==='[data-tab]')return tabs;
      if(sel==='[data-site-view]')return siteViews;
      if(sel==='[data-location]')return locations;
      return [];
    },
    createElement:()=>new NodeStub('created'),cookie:''
  };
  const dateParts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Kyiv',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const f=Object.fromEntries(dateParts.map(x=>[x.type,x.value]));
  const current=`${f.year}-${f.month}-${f.day}`;
  const payload=makePayload(current);
  const events=[];
  const window={
    scrollY:0,location:{href:'https://epicman1997.github.io/nashe-svitlo/'},
    addEventListener:(k,fn)=>{windowEvents[k]=fn;},
    dispatchEvent:ev=>{events.push(ev);windowEvents[ev.type]?.(ev);}
  };
  const context={window,document,location:window.location,
    navigator:{},console,URL,Date,Intl,
    setInterval(){return 1;},clearInterval(){},setTimeout(){return 1;},clearTimeout(){},
    localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,String(v))},
    CustomEvent:class{constructor(type,opts){this.type=type;this.detail=opts?.detail;}},
    fetch:async url=>({ok:true,json:async()=>String(url).includes('season.json')?{
      season:'2026/27',basis:'confirmed_schedules_not_actual_outages',
      locations:Object.fromEntries(Object.keys(payload.locations).map(k=>[k,{name:k,recorded_days:0}]))
    }:payload})
  };
  vm.runInNewContext(source,context);
  return {node,tabs,siteViews,locations,payload,events,context,windowEvents};
}

test('dashboard initializes, shows loaded schedules and an emergency beside the graph',async()=>{
  const r=runDashboard();
  await new Promise(setImmediate);
  assert.match(r.node('display').innerHTML,/graph/);
  assert.match(r.node('display').innerHTML,/07:30/);
  r.locations[1].events.click();
  assert.match(r.node('display').innerHTML,/Екстрені відключення/);
  assert.match(r.node('display').innerHTML,/Плановий графік/);
  assert.match(r.node('display').innerHTML,/07:30/);
  assert.equal(r.node('locationLabel').textContent,'Дім');
});

test('unknown tomorrow does not invent intervals, city tabs remain switchable',async()=>{
  const r=runDashboard();
  await new Promise(setImmediate);
  r.tabs[1].events.click();
  assert.match(r.node('display').innerHTML,/Графіка немає/);
  assert.doesNotMatch(r.node('display').innerHTML,/class="off"/);
  r.locations[3].events.click();
  assert.equal(r.node('locationLabel').textContent,'Науменки');
  assert.match(r.node('display').innerHTML,/Графіка немає/);
});

test('season view can load records without crashing the scheduling view',async()=>{
  const r=runDashboard();
  await new Promise(setImmediate);
  r.siteViews[1].events.click();
  await new Promise(setImmediate);
  assert.equal(r.node('seasonPanel').hidden,false);
  assert.equal(r.node('ecoflow').hidden,true);
  assert.match(r.node('seasonContent').innerHTML,/Сезон/);
  r.siteViews[0].events.click();
  assert.equal(r.node('ecoflow').hidden,false);
});
