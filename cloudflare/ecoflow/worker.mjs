// Read-only, on-demand EcoFlow REST collector. Never returns credentials, serials or raw quotas.
const SITE_ORIGIN = 'https://epicman1997.github.io';
const API = 'https://api-e.ecoflow.com';
const LIST = '/iot-open/sign/device/list', QUOTA = '/iot-open/sign/device/quota/all';
const BINDINGS = Object.freeze({
  "dacha:d2": "aa358ffa99bc686ecd078e4e811065adf0803526dd13e66dad24f9004eeddf30",
  "solovky:d2": "d24c12954582cbdf8ccb5620662ea2967a0c7be83b0d2cd0364ec4d8adebfe16",
  "naumenky:d2": "0bef920a44996b365ef81e3d6bd38c7c4e37a2e089e8abf41a6af218222d4013"
});
const MIN_MS = 60000; // Start conservatively; shorten only after checking upstream limits.
const MAX_MS = 15*60000;
const FIELDS = {
  dp3: {socPercent:['cmsBattSoc'],inputW:['powInSumW'],outputW:['powOutSumW'],runtimeMinutes:['cmsDsgRemTime']},
  d2: {socPercent:['pd.soc'],inputW:['pd.wattsInSum'],outputW:['pd.wattsOutSum'],runtimeMinutes:['pd.remainTime','bms_emsStatus.dsgRemainTime']}
};
const RANGES={socPercent:[0,100],inputW:[0,20000],outputW:[0,20000],runtimeMinutes:[1,10080]};
const encoder=new TextEncoder();
async function hmac(secret,message) {
  const key=await crypto.subtle.importKey('raw',encoder.encode(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const bytes=new Uint8Array(await crypto.subtle.sign('HMAC',key,encoder.encode(message)));
  return Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');
}
export async function signedHeaders(access,secret,query={},nonce=String(100000+crypto.getRandomValues(new Uint32Array(1))[0]%900000),timestamp=String(Date.now())) {
  const headers={accessKey:access,nonce,timestamp};
  const canonical=o=>Object.keys(o).sort().map(k=>k+'='+o[k]).join('&');
  const sign=await hmac(secret,[canonical(query),canonical(headers)].filter(Boolean).join('&'));
  return {...headers,sign};
}
class ApiError extends Error {
  constructor(kind){super(kind);this.kind=kind;}
}
export async function requestApi(env,path,query={}) {
  if(![LIST,QUOTA].includes(path))throw new ApiError('invalid_endpoint');
  const url=new URL(API+path);
  for(const [k,v] of Object.entries(query))url.searchParams.set(k,v);
  let headers;
  try {headers=await signedHeaders(env.ECOFLOW_ACCESS_KEY.trim(),env.ECOFLOW_SECRET_KEY.trim(),query);}
  catch {throw new ApiError('signing_error');}
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),15000);
  try {
    let res;
    // Workers does not implement redirect:'error'. Manual mode avoids forwarding
    // signed credentials to any redirect destination, including a different host.
    try {res=await fetch(url,{method:'GET',headers,signal:controller.signal,redirect:'manual'});}
    catch {throw new ApiError(controller.signal.aborted?'timeout':'network');}
    if(res.status>=300&&res.status<400)throw new ApiError('unexpected_redirect');
    if(res.status===429)throw new ApiError('rate_limited');
    if(!res.ok)throw new ApiError('http_'+res.status);
    let raw;
    try {raw=await res.json();}catch{throw new ApiError(controller.signal.aborted?'timeout':'invalid_data');}
    if(!raw||typeof raw!=='object'||Array.isArray(raw))throw new ApiError('invalid_data');
    const code=String(raw.code??'0');
    if(!['0','200'].includes(code))throw new ApiError(/^\d{1,7}$/.test(code)?'api_code_'+code:'api_error');
    return raw.data;
  } finally {clearTimeout(timer);}
}
function nestedGet(raw,path) {
  if(raw&&Object.hasOwn(raw,path))return raw[path];
  return path.split('.').reduce((v,k)=>v&&typeof v==='object'&&Object.hasOwn(v,k)?v[k]:undefined,raw);
}
function validNumber(value,field){
  const [lo,hi]=RANGES[field];return typeof value==='number'&&Number.isFinite(value)&&value>=lo&&value<=hi;
}
export function normalize(raw,kind,stamp) {
  if(!raw||typeof raw!=='object'||Array.isArray(raw))return null;
  const blob=raw.params&&typeof raw.params==='object'?raw.params:raw.data&&typeof raw.data==='object'?(raw.data.params??raw.data):raw;
  const reading={updatedAt:stamp};
  for(const [field,paths] of Object.entries(FIELDS[kind])) {
    for(const path of paths){const val=nestedGet(blob,path);if(validNumber(val,field)){reading[field]=field==='socPercent'?Math.round(val*10)/10:val;break;}}
  }
  if(!Object.hasOwn(reading,'socPercent'))return null;
  const i=reading.inputW,o=reading.outputW;
  reading.operation=i===0&&o===0?'holding':i>0&&o===0?'charging':i===0&&o>0?'discharging':'unknown';
  return reading;
}
function model(d) {
  for(const v of [d.productName,d.productType,d.deviceName,d.name]){
    if(typeof v!=='string')continue;
    const s=v.toUpperCase().replace(/[-_]/g,' ').replace(/\s+/g,' ');
    if(s.includes('DELTA PRO 3'))return 'dp3';
    if(s.includes('DELTA 2 MAX'))return null;
    if(s.includes('DELTA 2'))return 'd2';
    if(/DELTA 3|RIVER|POWER ?OCEAN/.test(s))return null;
  }
  return null;
}
function extractDevices(data){
  if(Array.isArray(data))return data;
  for(const k of ['list','devices','deviceList','items'])if(Array.isArray(data?.[k]))return data[k];
  throw new ApiError('invalid_data');
}
function emptyFrame(){return {version:1,emittedAt:new Date().toISOString(),mode:'worker-poll',devices:{},availability:{
  'dacha:dp3':'not_listed','dacha:dp3eb':'unavailable','dacha:d3p':'unsupported','dacha:d2':'not_listed','dacha:r3pw':'unsupported',
  'home:po':'unsupported','solovky:d2':'not_listed','solovky:d2eb':'unavailable','solovky:r2':'unsupported','naumenky:d2':'not_listed'},unassigned:[],connection:'ok'};}
async function collect(env){
  if(!env.ECOFLOW_ACCESS_KEY||!env.ECOFLOW_SECRET_KEY)throw new ApiError('missing_secrets');
  const frame=emptyFrame();
  const list=extractDevices(await requestApi(env,LIST)).filter(d=>d&&typeof d==='object'&&typeof d.sn==='string'&&d.sn);
  const dp3Count=list.filter(d=>model(d)==='dp3').length;
  const mapped=new Map(),duplicates=new Set();
  for(const d of list){
    const kind=model(d);
    let key=null;
    if(kind==='dp3'&&dp3Count===1)key='dacha:dp3';
    if(kind==='d2'){
      const fp=await hmac(env.ECOFLOW_SECRET_KEY.trim(),'nashe-svitlo/ecoflow-device-key/v1:'+d.sn);
      key=Object.keys(BINDINGS).find(k=>BINDINGS[k]===fp);
    }
    if(!key)continue;
    if(mapped.has(key)){duplicates.add(key);continue;}
    mapped.set(key,{serial:d.sn,kind});
  }
  let problem=null;
  for(const [key,{serial,kind}] of mapped){
    if(duplicates.has(key)){frame.availability[key]='invalid_data';continue;}
    try{
      const quota=await requestApi(env,QUOTA,{sn:serial});
      const reading=normalize(quota,kind,new Date().toISOString());
      if(!reading){frame.availability[key]='invalid_data';problem=problem??'invalid_data';continue;}
      frame.devices[key]=reading;frame.availability[key]='readable';
    }catch(err){
      const reason=err instanceof ApiError?err.kind:'api_error';
      frame.availability[key]=reason==='rate_limited'?'rate_limited':'api_error';
      problem=reason;
      if(reason==='rate_limited')break;
    }
  }
  frame.emittedAt=new Date().toISOString();
  frame.connection=Object.keys(frame.devices).length?'ok':'unavailable';
  return {frame,problem:problem??(Object.keys(frame.devices).length<4?'incomplete_devices':null)};
}
function json(value,status=200,extra={}){return new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',...extra}});}
export class TelemetryGate {
  constructor(state,env){this.state=state;this.env=env;this.inFlight=null;}
  async refresh(){
    const prior=await this.state.storage.get('state')??{};
    if(Date.now()<(prior.nextAt??0)&&!(prior.problem==='network'&&!prior.transportVersion))return prior;
    // Persist a global lock before calling the provider; even object restarts cannot cause a burst.
    await this.state.storage.put('state',{...prior,transportVersion:2,nextAt:Date.now()+MIN_MS});
    let frame=prior.frame??null,problem=null;
    try{const result=await collect(this.env);problem=result.problem;if(result.frame.connection==='ok'||!frame)frame=result.frame;else problem=problem??'no_readings';}
    catch(err){problem=err instanceof ApiError?err.kind:'api_error';}
    const delay=problem?Math.min(MAX_MS,Math.max(MIN_MS*2,(prior.delay??MIN_MS)*2)):MIN_MS;
    const next={frame,problem,delay,nextAt:Date.now()+delay,transportVersion:2};
    await this.state.storage.put('state',next);
    return next;
  }
  async fetch(request){
    if(!this.inFlight){this.inFlight=this.refresh().finally(()=>{this.inFlight=null;});}
    const s=await this.inFlight;
    if(new URL(request.url).pathname==='/health'){
      return json({status:s.frame?.connection==='ok'&&!s.problem?'ok':s.frame?'degraded':'unavailable',devices:Object.keys(s.frame?.devices??{}).length,emittedAt:s.frame?.emittedAt??null,problem:s.problem??null,refreshSeconds:Math.ceil((s.delay??MIN_MS)/1000)});
    }
    if(!s.frame)return json({error:'telemetry_unavailable'},503);
    return json(s.frame);
  }
}
export default {
  async fetch(request,env){
    const url=new URL(request.url);
    const origin=request.headers.get('Origin');
    const cors={'Access-Control-Allow-Origin':SITE_ORIGIN,'Vary':'Origin'};
    if(request.method==='OPTIONS'&&url.pathname==='/snapshot'&&origin===SITE_ORIGIN)return new Response(null,{status:204,headers:{...cors,'Access-Control-Allow-Methods':'GET, OPTIONS','Access-Control-Max-Age':'600'}});
    if(request.method!=='GET')return json({error:'method_not_allowed'},405);
    if(!['/snapshot','/health'].includes(url.pathname))return json({service:'nashe-svitlo-ecoflow',mode:'read-only',health:'/health'});
    if(url.pathname==='/snapshot'&&origin!==SITE_ORIGIN)return json({error:'origin_not_allowed'},403);
    try{
      const stub=env.TELEMETRY.get(env.TELEMETRY.idFromName('global-v1'));
      const response=await stub.fetch('https://internal'+url.pathname);
      const headers=new Headers(response.headers);
      if(url.pathname==='/snapshot')for(const [k,v] of Object.entries(cors))headers.set(k,v);
      return new Response(response.body,{status:response.status,headers});
    }catch{return json({error:'gateway_unavailable'},503,url.pathname==='/snapshot'?cors:{});}
  }
};
