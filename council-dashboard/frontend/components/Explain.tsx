'use client';
import {Snapshot,fmt,realHours} from '../lib/mission';
export function HowItWorks({snap}:{snap:Snapshot}){
 const s=snap.state;const running=s.jobs.filter(j=>j.status==='running');
 const next=running.map(j=>{const rate=j.done>0&&j.started_tick!==null&&s.tick>j.started_tick?j.done/(s.tick-j.started_tick):null;return {j,ticks:rate?Math.ceil((j.target-j.done)/rate):null};}).filter(x=>x.ticks!==null).sort((a,b)=>a.ticks!-b.ticks!)[0];
 const hrs=next?realHours(next.ticks!,snap.seconds_per_tick):null;
 return <section className="how-it-works">
  <div className="how-lead"><span className="eyebrow">WHAT THIS IS</span><h2>An autonomous robotic team preparing a Mars outpost, decided by Meta models.</h2>
   <p>Meta agents (muse-spark-1.3 specialists, a muse-wonder-1.0 director) run onboard at the outpost: they decide which work to start, which robots to assign and when batteries must be recharged, and act at once on live conditions without waiting for Earth. The real Deep Space Network and light-time delay only govern when Earth can hear from the outpost. A simulator checks every decision against published engineering data and records the result. Nothing is scripted; every model call is logged with Meta’s request ID.</p></div>
  <div className="how-grid">
   <div><small>NEXT AGENT DECISION</small><strong>{s.planning_needed?'Now':next?`When ${next.j.title.toLowerCase()} finishes`:'At the next completion or fault'}</strong><span>{next&&hrs!==null?`≈ ${fmt(hrs,1)} h real time (${next.ticks} steps)`:'Agents plan at genesis, after every completed job or fault, at solar conjunction, at a change of season, and on resume.'}</span></div>
  </div>
  <div className="how-truth"><span><Tag kind="measured"/>spacecraft imagery, DSN antenna activity</span><span><Tag kind="published"/>cited engineering values</span><span><Tag kind="computed"/>Mars date, Earth–Mars geometry</span><span><Tag kind="modeled"/>robot work, progress, power, cost</span><span><Tag kind="assumed"/>decisions D1–D18</span><span><Tag kind="estimated"/>weather between measurements</span><span><Tag kind="model"/>agent text, SAM detections</span><span><Tag kind="generated"/>Muse Image pictures</span></div>
 </section>;
}
export function Legend({only}:{only?:('status'|'values'|'images'|'detections'|'models')[]}){
 const show=(k:string)=>!only||only.includes(k as never);
 return <details className="legend"><summary>Legend</summary><div className="legend-grid">
  {show('status')&&<div><h4>Work status</h4><p><span className="badge pending">pending</span> planned, not started</p><p><span className="badge blocked">blocked</span> waiting on a prerequisite, equipment or power</p><p><span className="badge review">review</span> authorized onboard, awaiting onboard assurance; starts as soon as it is approved</p><p><span className="badge running">running</span> received on Mars and progressing</p><p><span className="badge complete">complete</span> target reached in the simulator</p></div>}
  {show('values')&&<div><h4>Where numbers come from</h4><p><b>published</b>: quoted from a cited source, page given</p><p><b>derived</b>: calculated from other values; formula shown</p><p><b>computed</b>: IAPWS water density</p><p><b>decision D1–D18</b>: owner-approved assumption, documented</p></div>}
  {show('images')&&<div><h4>Pictures</h4><p><b className="tag real">Observation</b> real spacecraft imagery (HiRISE)</p><p><b className="tag art">AI illustration</b> Muse Image drawing of recorded state</p><p><b className="tag sim">Layout</b> 3D stand-in models; positions are display-only</p></div>}
  {show('detections')&&<div><h4>SAM overlays</h4><p><i className="swatch" style={{background:'#f2b134'}}/> boulders</p><p><i className="swatch" style={{background:'#58c4dd'}}/> impact craters</p><p>Model detections on orbital imagery, not ground truth.</p></div>}
  {show('models')&&<div><h4>Meta models</h4><p><b>muse-spark-1.3</b> specialists and assurance</p><p><b>muse-wonder-1.0</b> mission director</p><p><b>muse-image-1.0</b> site illustrations</p><p><b>sam-3.1</b> orbital image segmentation</p></div>}
 </div></details>;
}

const TAGS:Record<string,[string,string,string]>={
 measured:['tag real','Measured','Instrument observation (spacecraft or ground station)'],
 published:['tag real','Published','Quoted from a cited source; page given'],
 computed:['tag real','Computed','Calculated from published values or standard algorithms'],
 modeled:['tag sim','Modeled','Output of this simulator from the cited inputs'],
 assumed:['tag assumed','Assumed','Owner-approved decision (D1–D18), not a measurement'],
 model:['tag art','Model output','Produced by an AI model; not ground truth'],
 estimated:['tag unverified','Estimated','Statistical estimate from the station history, with a 95 % interval; not a measurement'],
 checked:['tag real','Checked','An earlier estimate compared with the measurement that arrived later'],
 generated:['tag art','AI illustration','Generated picture of simulated state; not evidence']};
export function Tag({kind}:{kind:keyof typeof TAGS|string}){const t=TAGS[kind];return t?<b className={t[0]} title={t[2]}>{t[1]}</b>:null;}
export const paramTag=(c:string)=>c==='published'?'published':c==='computed'?'computed':'computed';
