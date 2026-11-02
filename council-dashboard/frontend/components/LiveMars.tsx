'use client';
import {useEffect,useState} from 'react';
import {LiveEnvironment,MarsConditions,fmt,hhmm} from '../lib/mission';
import {Tag} from './Explain';
const when=(t?:number|null)=>t?new Date(t*1000).toLocaleString():'never';
export function useLiveMars(){
 const [data,setData]=useState<LiveEnvironment|null>(null);const [error,setError]=useState('');
 useEffect(()=>{let live=true;const load=()=>fetch('/api/v1/environment/live').then(r=>r.ok?r.json():r.text().then(t=>{throw new Error(t)})).then(d=>{if(live){setData(d);setError('');}}).catch(e=>live&&setError(String(e)));
  load();const id=setInterval(load,60000);return()=>{live=false;clearInterval(id);};},[]);
 return {data,error};
}
function Conditions({c}:{c:MarsConditions}){
 return <div className="live-grid">
  <div><small><Tag kind="computed"/> MARS DATE</small><strong>Year {c.clock.mars_year} · Ls {fmt(c.clock.ls_deg,1)}°</strong><span>{c.clock.season}{c.clock.dusty_season?' · dusty season (Ls ≥ 135°)':''} · sol date {fmt(c.clock.mars_sol_date,2)}</span></div>
  <div><small>LOCAL TIME AT THE SITE</small><strong>{hhmm(c.clock.site_lmst_h)} LMST</strong><span>{c.site.latitude}° N, {c.site.longitude_east}° E (scenario site) · sun {c.clock.site_solar_elevation_deg>0?`up, ${fmt(c.clock.site_solar_elevation_deg,1)}° high`:`down (${fmt(c.clock.site_solar_elevation_deg,1)}°)`}</span></div>
  <div><small><Tag kind="computed"/> EARTH → MARS</small><strong>{fmt(c.geometry.one_way_light_s/60,1)} light-minutes</strong><span>{fmt(c.geometry.earth_mars_km/1e6,1)} million km · Sun–Mars {fmt(c.geometry.sun_mars_separation_deg,1)}° apart from Earth</span></div>
  <div className={c.link.conjunction?'live-alert':''}><small>SOLAR CONJUNCTION</small><strong>{c.link.conjunction?'In conjunction: uplinks held':'Clear'}</strong><span>Uplinks stop inside {c.link.conjunction_threshold_deg}° of the Sun (D10)</span></div>
 </div>;
}
export default function LiveMars({missionStatus}:{missionStatus:string}){
 const {data,error}=useLiveMars();
 if(error)return <section className="live-mars"><h2>Mars right now</h2><p role="alert">Live conditions unavailable: {error}</p></section>;
 if(!data)return <section className="live-mars"><h2>Mars right now</h2><p>Loading live conditions…</p></section>;
 const dsn=data.dsn;const up=(dsn?.links||[]).filter(l=>l.direction==='up');const down=(dsn?.links||[]).filter(l=>l.direction==='down');
 return <section className="live-mars">
  <div className="live-head"><div><span className="eyebrow">LIVE · UPDATES EVERY MINUTE{missionStatus!=='active'?' · MISSION PAUSED':''}</span><h2>Mars right now.</h2>
   <p>{missionStatus==='active'?'These conditions are applied to the mission at every tick. Agent work orders are sent from Earth and wait for a real DSN uplink to Mars.':'The mission is paused, but Mars keeps moving. Everything below is recorded and applied when the mission resumes; the agents then replan.'}</p></div>
   <span>{dsn&&!dsn.error&&dsn.checked_at?<><Tag kind="measured"/> DSN Now read</>:<b className="tag sim">DSN Now: unavailable</b>}</span></div>
  {data.error&&<p role="alert">Could not compute conditions: {data.error}</p>}
  {data.conditions_status?.error&&<p role="alert">Public mission halted: live conditions failed ({data.conditions_status.error})</p>}
  {data.now&&<Conditions c={data.now}/>}
  <div className="dsn-box"><h3>Deep Space Network, now</h3>
   {!dsn?<p>No DSN reading yet; the worker reads DSN Now every minute.</p>:dsn.error?<p role="alert">DSN Now unreachable since {when(dsn.failed_at)}: {dsn.error}. Work orders are not held by DSN while the feed is down (D10).</p>:<>
   <p>{up.length?`Uplink to Mars active: ${up.map(l=>`${l.station} ${l.dish} → ${l.spacecraft}${l.data_rate_bps?` (${fmt(l.data_rate_bps,0)} b/s)`:''}`).join(', ')}.`:'No uplink to Mars right now.'} {down.length?`Receiving from ${[...new Set(down.map(l=>l.spacecraft))].join(', ')}.`:''}</p>
   <small>Last uplink to Mars: {when(dsn.last_mars_uplink_at)} · read {when(dsn.checked_at)} · spacecraft at Mars identified by their DSN mission abbreviation (JPL DSN mission set: MRO, M01O, MVN, M20, MSL, TGO, MEX, EMM, MOM); the live feed currently publishes no ranges.</small>
   <details className="dsn-raw"><summary><Tag kind="measured"/> What the feed contained ({dsn.dishes_in_feed??'?'} dishes, {dsn.targets_seen?.length??'?'} targets) — check against <a href="https://eyes.nasa.gov/dsn/dsn.html" target="_blank" rel="noreferrer">NASA DSN Now</a></summary>
    <table><thead><tr><th>Station · dish</th><th>Target</th><th>Mission</th><th>Range (km)</th><th>At Mars?</th><th>Up</th><th>Down</th></tr></thead><tbody>{(dsn.targets_seen||[]).slice(0,14).map((t,i)=><tr key={i}><td>{t.station} {t.dish}</td><td>{t.target}</td><td>{t.mission||'—'}</td><td>{t.range_km===null?'not published':fmt(t.range_km,0)}</td><td>{t.at_mars?'yes':'no'}</td><td>{t.up_active?'active':'—'}</td><td>{t.down_active?'active':'—'}</td></tr>)}</tbody></table></details></>}
  </div>
  {data.observations.length>0&&<details className="obs-log"><summary>Recorded changes ({data.observations.length})</summary><ul>{data.observations.map(o=><li key={o.id}><time>{when(o.observed_at)}</time> {o.kind==='dsn-unavailable'?`DSN feed unavailable: ${o.error}`:`${o.uplink_to_mars?'Uplink to Mars':'No uplink'} · ${o.downlink_from_mars?'downlink from Mars':'no downlink'}${o.mars_spacecraft?.length?` · ${o.mars_spacecraft.join(', ')}`:''}`}</li>)}</ul></details>}
  <p className="live-note">Real: Mars date and season (Mars24, NASA GISS), Earth–Mars geometry (IAU ERFA), DSN antenna activity (NASA DSN Now). The outpost itself is simulated; dust and season change no work rates (D11: fission power is unaffected by dust, and no published dust or frost penalty exists for these machines).</p>
 </section>;
}
