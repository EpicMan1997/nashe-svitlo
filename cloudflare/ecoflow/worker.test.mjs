import test from 'node:test';
import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';
import worker,{signedHeaders,normalize,TelemetryGate,requestApi} from './worker.mjs';
test('HMAC matches existing Python signing order',async()=>{
 const h=await signedHeaders('access','secret',{sn:'test-device'},'123456','1234567890');
 assert.equal(h.sign,createHmac('sha256','secret').update('sn=test-device&accessKey=access&nonce=123456&timestamp=1234567890').digest('hex'));
});
test('combined SOC and zero watts remain correct; no missing values invented',()=>{
 assert.deepEqual(normalize({cmsBattSoc:39.9,powInSumW:0,powOutSumW:506},'dp3','stamp'),{updatedAt:'stamp',socPercent:39.9,inputW:0,outputW:506,operation:'discharging'});
 assert.deepEqual(normalize({'pd.soc':80,'pd.wattsInSum':0,'pd.wattsOutSum':0},'d2','stamp'),{updatedAt:'stamp',socPercent:80,inputW:0,outputW:0,operation:'holding'});
 assert.equal(normalize({'pd.soc':false},'d2','stamp'),null);
 assert.equal(normalize({'pd.soc':80},'d2','stamp').outputW,undefined);
});
test('public interface blocks writes and unexpected browser origins',async()=>{
 assert.equal((await worker.fetch(new Request('https://test/snapshot'),{})).status,403);
 assert.equal((await worker.fetch(new Request('https://test/snapshot',{method:'POST'}),{})).status,405);
});
test('missing keys back off globally without emitting invented readings',async()=>{
 const map=new Map(),storage={get:async k=>map.get(k),put:async(k,v)=>{map.set(k,v);}};
 const gate=new TelemetryGate({storage},{});
 const a=await (await gate.fetch(new Request('https://internal/health'))).json();
 const b=await (await gate.fetch(new Request('https://internal/health'))).json();
 assert.equal(a.problem,'missing_secrets');assert.equal(a.devices,0);assert.equal(a.refreshSeconds,120);
 assert.deepEqual(b,a);
});

test('root endpoint identifies the deployed gateway without contacting EcoFlow',async()=>{
 const response=await worker.fetch(new Request('https://test/'),{});
 assert.equal(response.status,200);
 assert.deepEqual(await response.json(),{service:'nashe-svitlo-ecoflow',mode:'read-only',health:'/health'});
 assert.equal(response.headers.get('Cache-Control'),'no-store');
});

test('Cloudflare-compatible transport never follows redirects or forwards credentials',async t=>{
 const previous=globalThis.fetch;
 t.after(()=>{globalThis.fetch=previous;});
 let calls=0;
 globalThis.fetch=async (url,opts)=>{
  calls++;
  assert.equal(opts.redirect,'manual');
  assert.equal(opts.method,'GET');
  assert.equal(url.hostname,'api-e.ecoflow.com');
  assert.ok(opts.headers.sign);
  return new Response(null,{status:302,headers:{Location:'https://untrusted.invalid/'}});
 };
 const env={ECOFLOW_ACCESS_KEY:'access',ECOFLOW_SECRET_KEY:'secret'};
 await assert.rejects(requestApi(env,'/iot-open/sign/device/list'),{message:'unexpected_redirect'});
 assert.equal(calls,1);
 globalThis.fetch=async()=>new Response(JSON.stringify({code:1000,message:'private data never returned'}),{status:200});
 await assert.rejects(requestApi(env,'/iot-open/sign/device/list'),{message:'api_code_1000'});
 globalThis.fetch=async()=>new Response(JSON.stringify({code:0,data:[]}),{status:200});
 assert.deepEqual(await requestApi(env,'/iot-open/sign/device/list'),[]);
});
