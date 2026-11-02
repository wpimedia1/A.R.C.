'use client';
import {useEffect,useState} from 'react';
import {api,solOf} from '../lib/mission';
import {Tag} from './Explain';
type Cycle={cycle_id:string;tick:number;mean_pairwise_agreement:number|null;agents:string[];propositions:number;consensus_jobs:Record<string,{judgement:string;outcome:string}>;shared_missing_information:{item:string;roles:string[]}[];possible_correlated_error:boolean;consensus_with_bad_outcome:string[]};
export default function Evaluation({mid,revision}:{mid:string;revision:number}){
 const [d,setD]=useState<{cycles:Cycle[];summary:{cycles:number;flagged:number;mean_agreement:number|null}}|null>(null);const [error,setError]=useState('');
 useEffect(()=>{api<typeof d>(`missions/${mid}/evaluation`).then(x=>{setD(x);setError('');}).catch(e=>setError(e.message));},[mid,revision]);
 return <section className="evaluation"><h2>Do independent assessments catch each other’s mistakes?</h2>
  <p><Tag kind="computed"/> Each planning cycle, every agent independently judges every open job: proceed now or hold. Agreement is the share of jobs two agents judged the same way, averaged over all pairs. A unanimous “proceed” on work later held by assurance or stopped is flagged as a possible shared (correlated) error.</p>
  {error&&<p role="alert">{error}</p>}
  {d&&(d.cycles.length?<><p>{d.summary.cycles} cycles · mean agreement {d.summary.mean_agreement??'—'} · {d.summary.flagged} flagged</p>
   <table><thead><tr><th>Cycle</th><th>Agreement</th><th>Unanimous judgement → outcome</th><th>Shared gaps</th></tr></thead><tbody>{d.cycles.slice().reverse().map(c=><tr key={c.cycle_id} className={c.possible_correlated_error?'flagged':''}><td>{solOf(c.tick)}</td><td>{c.mean_pairwise_agreement??'—'}<br/><small>{c.agents.length} agents · {c.propositions} jobs</small></td><td>{Object.entries(c.consensus_jobs).map(([j,o])=>`${j}: ${o.judgement} → ${o.outcome}`).join('; ')||'none'}</td><td>{c.shared_missing_information.map(g=>`${g.item} (${g.roles.join(', ')})`).join('; ')||'none'}</td></tr>)}</tbody></table></>
   :<p>No planning cycles recorded yet.</p>)}</section>;
}
