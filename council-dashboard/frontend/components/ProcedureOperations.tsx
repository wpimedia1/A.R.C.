'use client';
import {useState} from 'react';
import {State,fmt} from '../lib/mission';

export function ProcedureOperations({s}:{s:State}){
 const jobs=s.jobs.filter(j=>j.procedure);
 return <section className="procedure-operations"><h2>Service and payload operations</h2>
 <p>Repairs consume a compatible spare. Battery exchange preserves both packs. Offload occupies lifting equipment before shielding can begin.</p>
 {s.charging_policies&&<details><summary>Agent-authorized routine charging</summary><ul>{Object.entries(s.charging_policies).map(([id,p])=><li key={id}><strong>{id}</strong>: {p.rule}<br/>{p.actor} · {p.reason}</li>)}</ul><p>The simulator executes these recorded standing orders within the normal power and equipment limits.</p></details>}
 {!s.procedure_configuration&&<p className="notice">No repair, swap or lifting design is configured in this mission. These operations cannot execute. Charging and complete-unit replacement are separate operations.</p>}
 {s.procedure_configuration&&<p>Engineering study <code>{s.procedure_configuration.hash.slice(0,12)}</code>. Operator-supplied designs and assumptions are recorded; they do not establish hardware qualification.</p>}
 {jobs.map(j=><article key={j.id}><h3>{j.title}</h3><p>{j.status} · {fmt(j.done)} of {fmt(j.target)} hours · target {j.procedure?.target_id}</p>
 <p>{j.reason||'Follow the work order for its authorization and result.'}</p>
 <ol>{j.procedure?.stages.map((stage,i)=><li key={i}>{stage.name}: {fmt(stage.duration.value)} h, {fmt(stage.grid_power.value)} kW · {stage.duration.origin}</li>)}</ol>
 {j.procedure?.execution&&<p>Recorded grid energy: {fmt(j.procedure.execution.reduce((n,e)=>n+e.grid_energy_kwh,0),3)} kWh</p>}</article>)}
 {s.inventory&&<details><summary>Spare manifest and reservations</summary><ul>{Object.values(s.inventory).map(i=><li key={i.id}><strong>{i.id}</strong> · {i.kind} · {i.status}{i.reserved_by?` · reserved for ${i.reserved_by}`:''}{i.soc_wh!=null?` · ${fmt(i.soc_wh)} Wh`:''}</li>)}</ul></details>}
 {s.equipment_physics&&<details><summary>Calculated equipment temperatures and energy</summary><p>These are engineering calculations, not local sensor measurements.</p><ul>{Object.entries(s.equipment_physics).map(([id,p])=><li key={id}>{id}: {fmt(p.temperature_k-273.15)} °C · housekeeping {fmt(p.cumulative_housekeeping_wh)} Wh · heater {fmt(p.cumulative_heater_wh)} Wh</li>)}</ul></details>}
 </section>;
}

export function ProcedureControls({s,busy,apply}:{s:State;busy:boolean;apply:(changes:unknown)=>void}){
 const [error,setError]=useState(''),[profile,setProfile]=useState(''),[services,setServices]=useState<string[]>([]),[spare,setSpare]=useState('');
 const profiles=Object.values(s.procedure_configuration?.profiles||{});
 const selected=profiles.find(p=>p.id===profile);
 async function load(file:File|undefined){
  if(!file)return;
  try{
   if(file.size>512000)throw new Error('Engineering input exceeds 512 kB');
   const payload=JSON.parse(await file.text());
   if(!payload||typeof payload!=='object'||Array.isArray(payload)||Object.keys(payload).some(k=>!['procedures','equipment_physics'].includes(k)))throw new Error('File must contain procedures and/or equipment_physics settings');
   setError('');apply(payload);
  }catch(e){setError(String(e));}
 }
 return <details><summary>Engineering design and service work</summary>
 <p>Configure your private engineering study with cited inputs or explicitly approved assumptions. No repair hardware, spare stock or operating time is invented automatically.</p>
 <label>Import engineering configuration (JSON)<input type="file" accept="application/json,.json" disabled={busy} onChange={e=>load(e.target.files?.[0])}/></label>
 {error&&<p role="alert">{error}</p>}
 {profiles.length>0&&<><label>Procedure<select value={profile} onChange={e=>{setProfile(e.target.value);setServices([]);setSpare('');}}><option value="">Choose a configured procedure</option>{profiles.map(p=><option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
 {selected&&<>{selected.kind==='repair'&&<button disabled={busy} onClick={()=>apply({component_faults:{[selected.target_id]:{component:selected.component,basis:'Owner-requested controlled component-failure experiment',approved:true}}})}>Inject component failure in this experiment</button>}<fieldset><legend>Compatible service equipment</legend>{Object.entries(s.procedure_configuration!.equipment).filter(([,d])=>d.interface===selected.interface).map(([id])=><label key={id}><input type="checkbox" checked={services.includes(id)} onChange={e=>setServices(e.target.checked?[...services,id]:services.filter(a=>a!==id))}/>{s.assets.find(a=>a.id===id)?.name||id}</label>)}</fieldset>
 {selected.kind!=='offload'&&<label>Spare serial<select value={spare} onChange={e=>setSpare(e.target.value)}><option value="">Choose an available spare</option>{Object.values(s.inventory||{}).filter(i=>i.status==='stored'&&!i.reserved_by&&i.interface===selected.interface&&i.compatible_asset_id===selected.target_id).map(i=><option key={i.id} value={i.id}>{i.id}</option>)}</select></label>}
 <button disabled={busy||!services.length||(selected.kind!=='offload'&&!spare)} onClick={()=>apply({procedure_order:{profile_id:profile,service_ids:services,spare_id:spare||null,summary:'Owner requested '+selected.title}})}>Create work order</button>
 <p>Creating work reserves the spare and target. The selected planner must still authorize the job; agent mode also requires onboard assurance.</p></>}
 </>}
 </details>;
}
