'use client';
import {useState} from 'react';
import {State} from '../lib/mission';
import {ProcedureControls} from './ProcedureOperations';

export default function ExperimentControls({s,busy,apply}:{s:State;busy:boolean;apply:(changes:unknown)=>void}){
 const [feed,setFeed]=useState(''),[storage,setStorage]=useState(''),[rate,setRate]=useState(''),[limit,setLimit]=useState('');
 function move(id:string,offset:number){const p=[...s.priority],i=p.indexOf(id),j=i+offset;if(j<0||j>=p.length)return;[p[i],p[j]]=[p[j],p[i]];apply({priority:p});}
 return <details><summary>Work priorities and experiment allocations</summary>
 <p>These settings change your private scenario. Allocations describe the experiment; they are not new measurements of Mars.</p>
 <ol>{s.priority.map((id,i)=><li key={id}>{s.jobs.find(j=>j.id===id)?.title||id} <button disabled={busy||i===0} aria-label={`Prioritize ${id}`} onClick={()=>move(id,-1)}>Earlier</button><button disabled={busy||i===s.priority.length-1} aria-label={`Deprioritize ${id}`} onClick={()=>move(id,1)}>Later</button></li>)}</ol>
 {s.production&&<><p>Water stored: {s.production.water_stored_kg.toFixed(1)} kg. Feed remaining: {s.production.water_feed_remaining_kg.toFixed(1)} kg. Storage allocation: {s.production.water_storage_capacity_kg.toFixed(1)} kg.</p>
 <label>Water feed allocation remaining (kg)<input type="number" min="0" value={feed} onChange={e=>setFeed(e.target.value)}/></label><button disabled={busy||feed===''} onClick={()=>apply({production:{water_feed_remaining_kg:Number(feed)}})}>Apply feed</button>
 <label>Water storage allocation (kg)<input type="number" min={s.production.water_stored_kg} value={storage} onChange={e=>setStorage(e.target.value)}/></label><button disabled={busy||storage===''} onClick={()=>apply({production:{water_storage_capacity_kg:Number(storage)}})}>Apply storage</button>
 <label>Production fraction of published operating point (0–1)<input type="number" min="0" max="1" step="0.05" value={rate} onChange={e=>setRate(e.target.value)}/></label><button disabled={busy||rate===''} onClick={()=>apply({production:{rate_multiplier:Number(rate)}})}>Apply production</button></>}
 <label>Scenario operating expenditure limit (USD)<input type="number" min={s.spent_usd} value={limit} onChange={e=>setLimit(e.target.value)}/></label><button disabled={busy||limit===''} onClick={()=>apply({operating_spending_limit_usd:Number(limit)})}>Apply allocation</button><button disabled={busy} onClick={()=>apply({operating_spending_limit_usd:null})}>Clear allocation</button>
 <p>This controls scenario expenditure, not provider billing. All changes and their baseline comparisons are recorded.</p>
 <ProcedureControls s={s} busy={busy} apply={apply}/>
 </details>;
}
