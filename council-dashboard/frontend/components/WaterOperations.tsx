'use client';
import {State,fmt} from '../lib/mission';

export default function WaterOperations({s,select}:{s:State;select:(id:string)=>void}){
 const well=s.well,p=s.production;
 if(!well||!p)return null;
 return <section className="procedure-operations" aria-label="Water system operations">
  <h2>Establish the well, then deliver water.</h2>
  <p>The well keeps a working reserve. Water delivered to the outpost is counted separately.</p>
  <div className="inspection-grid">
   <div><small>Water delivered</small><strong>{fmt(p.water_stored_kg,2)} kg</strong></div>
   <div><small>Water retained in the well</small><strong>{fmt(well.contained_kg,2)} kg</strong></div>
   <div><small>Reserve qualified by the model</small><strong>{fmt(well.qualified_liquid_kg,2)} / {fmt(well.reserve_kg,2)} kg</strong></div>
   <div><small>Remaining ice allocation</small><strong>{fmt(p.water_feed_remaining_kg,2)} kg</strong></div>
  </div>
  <p><strong>Well state:</strong> {well.phase.replaceAll('-',' ')}. {well.phase==='requalification-required'?'Heat continuity was interrupted. Recondition the retained reserve before withdrawal.':''}</p>
  <ol>{s.jobs.filter(j=>j.id==='drill'||j.kind==='well-establishment'||j.kind==='water').map(j=><li key={j.id}><button className="text-link" onClick={()=>select(j.id)}>{j.title}: {j.status} · {fmt(j.done,2)} / {fmt(j.target,2)} {j.unit}</button></li>)}</ol>
  <details><summary>Model basis and limits</summary>
   <p>D21 is an explicit design-study assumption: a one-control-interval reserve, conditioned using effective energy calculated from the published steady-state operating point. Startup performance is extrapolated and requires calibration. These quantities are simulator calculations, not site instrument readings.</p>
   <p>Feed, retained water and delivered water are conserved together. Reconditioning consumes energy again without adding a second reserve. Hardware qualification and local resource confirmation remain separate requirements.</p>
  </details>
 </section>;
}
