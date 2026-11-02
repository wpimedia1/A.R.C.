'use client';
// Shows that the mission is running: state badge, clocks that tick every second, countdown to the next step,
// and the background worker's heartbeat (its DSN read every 60 s). All times come from the server; nothing is assumed.
import {useEffect,useState} from 'react';
import {Snapshot} from '../lib/mission';

type Live={now:{clock:{unix:number;site_ltst_h:number;site_lmst_h:number}}|null;dsn:{checked_at:number|null;error:string|null;last_mars_uplink_at?:number|null;mars_spacecraft?:string[];links?:{direction:string;spacecraft:string;station:string;dish:string}[]}|null};
const STALE_S=180; // the worker reads DSN every 60 s; three missed reads = not reporting

const dur=(s:number)=>{s=Math.max(0,Math.round(s));const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return (h?`${h}:`:'')+`${String(m).padStart(h?2:1,'0')}:${String(x).padStart(2,'0')}`;};
// Mars hours as hh:mm:ss (Mars-hour based, 24 per sol)
const clock=(h:number)=>{const t=Math.floor(h*3600);return [Math.floor(t/3600),Math.floor(t%3600/60),t%60].map(v=>String(v).padStart(2,'0')).join(':');};
const ago=(s:number)=>s<90?`${Math.round(s)} s ago`:s<5400?`${Math.round(s/60)} min ago`:`${Math.round(s/3600)} h ago`;

export function useLive(){
 const [live,setLive]=useState<Live|null>(null),[err,setErr]=useState('');
 useEffect(()=>{let on=true;const load=()=>fetch('/api/v1/environment/live').then(r=>r.ok?r.json():r.text().then(t=>{throw new Error(t)})).then(d=>{if(on){setLive(d);setErr('');}}).catch(e=>on&&setErr(String(e).slice(0,200)));
  load();const id=setInterval(load,30000);return()=>{on=false;clearInterval(id);};},[]);
 return {live,err};
}
export function useNow(){const [now,setNow]=useState(()=>Date.now()/1000);useEffect(()=>{const id=setInterval(()=>setNow(Date.now()/1000),1000);return()=>clearInterval(id);},[]);return now;}

export default function LiveStrip({snap}:{snap:Snapshot}){
 const {live,err}=useLive();const now=useNow();const s=snap.state;
 const hb=live?.dsn?.checked_at??null;const age=hb==null?null:now-hb;const workerOk=age!=null&&age<STALE_S;
 const state=s.status==='complete'?'COMPLETE':s.status!=='active'?s.status.toUpperCase():workerOk?'RUNNING':'NOT ADVANCING';
 const cls=state==='RUNNING'?'run':state==='COMPLETE'?'done':'stop';
 // Site local solar time advances one Mars hour per tick_seconds (sol / 24), counted from the server's reading.
 const c=live?.now?.clock;const mh=snap.seconds_per_tick||null;
 const ltst=c&&mh?((c.site_ltst_h+(now-c.unix)/mh)%24+24)%24:null;
 const next=snap.next_tick_at;const toNext=next!=null?next-now:null;
 const up=live?.dsn?.links?.filter(l=>l.direction==='up')||[];
 return <div className="live-strip" role="status" aria-live="off">
  <span className={'live-badge '+cls}><i/>{state}</span>
  <span><small>EARTH UTC</small><b>{new Date(now*1000).toISOString().slice(11,19)}</b></span>
  <span><small>MARS SITE LOCAL TIME</small><b>{ltst==null?'—':clock(ltst)}</b></span>
  <span><small>NEXT STEP (1 MARS HOUR)</small><b>{s.status!=='active'?'—':toNext==null?'—':toNext>0?`in ${dur(toNext)}`:`due · worker catching up`}</b></span>
  <span><small>WORKER</small><b className={workerOk?'ok':'bad'}>{age==null?(err?'unreachable':'no report yet'):workerOk?`active · DSN read ${ago(age)}`:`not reporting · last DSN read ${ago(age)}`}</b></span>
  <span><small>PLANNING</small><b className={s.inference_stopped?'bad':undefined}>{s.planning_status}</b></span>
  <span><small>EARTH CONTACT (DSN)</small><b>{up.length?`uplink now: ${up.map(l=>`${l.station} ${l.dish} → ${l.spacecraft}`).join(', ')}`:live?.dsn?.last_mars_uplink_at?`last uplink ${ago(now-live.dsn.last_mars_uplink_at)}`:'no uplink to Mars seen yet'}</b></span>
 </div>;
}
