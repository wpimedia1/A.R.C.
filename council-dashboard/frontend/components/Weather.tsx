'use client';
import {useEffect,useState} from 'react';
import {api,fmt} from '../lib/mission';
import {Tag} from './Explain';
type Est={value:number;low95:number;high95:number;target_sol:number;target_utc_approx:string;relation_to_now:string;basis:{method:string;climatology_mean:number;climatology_samples:number;ls_window_deg:number;span_sols:number;lag1_autocorrelation:number;lead_sols:number;newest_measured_sol:number;newest_measured_value:number}};
type Chk={target_sol:number;lead_sols:number;estimated:number;low95:number;high95:number;measured:number;error:number;status:string};
type Var={unit:string;measured:{value:number;sol:number;date:string}|null;estimate_today:Est|null;forecast:Est[];calibration:{checked:number;confirmed:number;interval_coverage:number|null;mean_abs_error:number|null;recent:Chk[]}};
type Station={station:string;location:string;source:string;newest_measured_sol:number;newest_measured_date:string;station_sol_now:number;data_delay_sols:number;sols_stored:number;variables:Record<string,Var>};
type Data={stations:Record<string,Station>;feeds:Record<string,unknown>|null};
const LABEL:Record<string,string>={air_min_c:'Air min',air_max_c:'Air max',pressure_pa:'Pressure',ground_min_c:'Ground min',ground_max_c:'Ground max'};
export default function Weather(){
 const [d,setD]=useState<Data|null>(null);const [error,setError]=useState('');
 useEffect(()=>{let live=true;const load=()=>api<Data>('environment/weather').then(x=>{if(live){setD(x);setError('');}}).catch(e=>live&&setError(e.message));load();const id=setInterval(load,120000);return()=>{live=false;clearInterval(id);};},[]);
 if(error)return <section className="weather"><h2>Mars surface weather</h2><p role="alert">{error}</p></section>;
 if(!d)return <section className="weather"><h2>Mars surface weather</h2><p>Loading…</p></section>;
 const stations=Object.values(d.stations);
 return <section className="weather"><div className="live-head"><div><span className="eyebrow">MEASURED → ESTIMATED → CHECKED</span><h2>Mars surface weather.</h2>
  <p>NASA publishes rover weather days to months late. The newest measurement is shown with its date; the gap to today is filled by a statistical estimate from the station’s own history (same season, recent anomaly), with a 95 % interval; when the real number arrives, every estimate made for that sol is marked confirmed or corrected. The agents reason over all three.</p></div></div>
  {!stations.length&&<p>{d.feeds?`No station data stored yet. Feed status: ${JSON.stringify(d.feeds)}`:'The worker reads the NASA weather feeds every 6 hours; nothing has been read yet.'}</p>}
  {stations.map(s=><article key={s.station} className="station"><h3>{s.station} <small>{s.location} · {s.sols_stored} sols stored · newest measurement sol {s.newest_measured_sol} ({s.newest_measured_date}) · station sol now ≈ {s.station_sol_now} · data delay {s.data_delay_sols} sols</small></h3>
   <table><thead><tr><th>Variable</th><th><Tag kind="measured"/> Newest measured</th><th><Tag kind="estimated"/> Estimate for today</th><th>Next 3 sols</th><th><Tag kind="checked"/> Track record</th></tr></thead><tbody>
   {Object.entries(s.variables).filter(([,v])=>v.measured).map(([k,v])=><tr key={k}><td>{LABEL[k]||k}<br/><small>{v.unit}</small></td>
    <td>{v.measured?<>{fmt(v.measured.value,1)}<br/><small>sol {v.measured.sol} · {v.measured.date}</small></>:'—'}</td>
    <td>{v.estimate_today?<>{fmt(v.estimate_today.value,1)} <small>[{fmt(v.estimate_today.low95,1)} … {fmt(v.estimate_today.high95,1)}]</small><br/><small>lead {v.estimate_today.basis.lead_sols} sols · {v.estimate_today.basis.climatology_samples} past sols within ±{v.estimate_today.basis.ls_window_deg}° Ls · r={v.estimate_today.basis.lag1_autocorrelation}</small></>:'—'}</td>
    <td>{v.forecast.length?v.forecast.map(f=><div key={f.target_sol}><small>sol {f.target_sol}: {fmt(f.value,1)} [{fmt(f.low95,1)}…{fmt(f.high95,1)}]</small></div>):'—'}</td>
    <td>{v.calibration.checked?<><b>{v.calibration.confirmed}/{v.calibration.checked}</b> inside the 95 % band · MAE {v.calibration.mean_abs_error}<br/>{v.calibration.recent.slice(-3).map(c=><small key={c.target_sol}>sol {c.target_sol}: est {fmt(c.estimated,1)} → meas {fmt(c.measured,1)} ({c.status})<br/></small>)}</>:<small>No estimate has been checked yet</small>}</td></tr>)}
   </tbody></table></article>)}
  <p className="live-note">Stations are hundreds to thousands of kilometres from the scenario site (40° N, 190° E); measurements describe Gale and Jezero craters, not Arcadia. Source: NASA public weather feeds (REMS data via CAB, outreach quality).</p>
 </section>;
}
