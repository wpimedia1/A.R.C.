'use client';
import {useState} from 'react';
import {ArrowRight,CheckCircle,BookOpen} from '@phosphor-icons/react';
import {State,Job,Snapshot,fmt,usd,solOf} from '../lib/mission';
import {Operations} from './OperationsPanels';
import {HowItWorks,Legend,Tag,paramTag} from './Explain';
import dynamic from 'next/dynamic';
const MissionScene=dynamic(()=>import('./MissionScene'),{ssr:false,loading:()=><p className="fallback">Loading the outpost…</p>});

const status=(j:Job)=>j.status==='complete'?'Complete':j.status==='running'?(/^(Paused|Standby|Night)/.test(j.reason||'')?'In progress · paused':'In progress'):j.status==='review'?'Awaiting onboard assurance':j.reason&&!j.reason.includes('Awaiting')?'Waiting':'Planned';

function ProgressChart({s,data,job}:{s:State;data:Operations|null;job:Job}){
 const rows=(data?.series||[]).filter(r=>typeof r[job.output]==='number');
 if(rows.length<2)return <p>The chart appears after the simulator records progress for this work.</p>;
 const t0=rows[0].tick,t1=rows.at(-1)!.tick,y=(v:number)=>160-v/job.target*140;
 return <><svg viewBox="0 0 800 190" role="img" aria-label={`${job.title}: ${fmt(job.done)} of ${fmt(job.target)} ${job.unit}`}>
  <line x1="42" x2="785" y1={y(job.target)} y2={y(job.target)} stroke="#b85c35" strokeDasharray="6 5"/><text x="0" y={y(job.target)+4} fill="#56635d" fontSize="12">target</text>
  <line x1="42" x2="785" y1="160" y2="160" stroke="#c7cec9"/>
  <polyline fill="none" stroke="#246b58" strokeWidth="4" points={rows.map(r=>`${42+(r.tick-t0)/Math.max(1,t1-t0)*743},${y(Number(r[job.output]))}`).join(' ')}/>
  <text x="44" y="185" fontSize="12" fill="#56635d">{solOf(t0)}</text><text x="695" y="185" fontSize="12" fill="#56635d">{solOf(t1)}</text></svg>
  <p>Dashed line: target of {fmt(job.target)} {job.unit}, from {job.parameters.join(', ')}. Simulator output, not a measurement on Mars.</p></>;
}

export default function MissionJourney({s,snap,data,select,navigate,mid}:{s:State;snap:Snapshot;data:Operations|null;select:(id:string)=>void;navigate:(tab:string)=>void;mid:string}){
 const running=s.jobs.filter(j=>j.status==='running');
 const [chosen,setChosen]=useState<string|null>(null);
 const job=s.jobs.find(j=>j.id===(chosen||running[0]?.id||s.jobs.find(j=>j.status!=='complete')?.id||s.jobs[0].id))!;
 const decision=s.decisions.find(d=>d.id===job.decision_id);
 const params=job.parameters.map(n=>({n,p:s.spec.parameters[n]}));
 return <div className="mission-journey">
  <section className="mission-summary" aria-label="Mission briefing"><div><span className="eyebrow">MISSION SIMULATOR · THE OBJECTIVE · {s.jobs.filter(j=>j.status==='complete').length} / {s.jobs.length} WORK ORDERS COMPLETE</span><h1>Prepare an outpost before people arrive.</h1><p>{s.spec.readiness.description}</p><button className="text-link" onClick={()=>navigate('Evidence')}>Inspect the mission evidence <ArrowRight/></button></div><div className="briefing-facts"><p><strong>{s.status==='active'?'Authorized work':'Mission paused · authorized work'}</strong>{running.length?running.map(j=>j.title).join(' · '):'No running work orders'}</p><p><strong>What needs to happen next</strong>{s.jobs.find(j=>j.reason&&j.status!=='complete')?.reason||job.basis}</p><p><strong>Latest recorded decision</strong>{s.decisions.at(-1)?.summary||'No work has been authorized yet.'}</p></div></section>
  <MissionScene snap={snap} mid={mid}/>
  <section className="activity-feed" aria-label="Latest activity"><h2>What just happened</h2>
   <ol>{s.activity.slice(-10).reverse().map(a=><li key={a.id}><time>{solOf(a.tick)}</time><div><strong>{a.title}</strong><p>{a.detail}</p></div></li>)}</ol>
   <button className="text-link" onClick={()=>navigate('Records')}>Complete history <ArrowRight/></button></section>
  <section id="mission-plan" className="journey-plan"><div className="journey-section-heading"><div><span className="eyebrow">01 / THE PLAN</span><h2>From landed equipment to a ready site.</h2></div><button onClick={()=>navigate('Evidence')}><BookOpen/> Sources</button></div>
   <div className="journey-timeline">{s.jobs.map((j,i)=><button key={j.id} className={`${job.id===j.id?'selected ':''}${j.status}`} aria-pressed={job.id===j.id} onClick={()=>setChosen(j.id)}><span className="timeline-number">{j.status==='complete'?<CheckCircle weight="fill"/>:`0${i+1}`}</span><strong>{j.title}</strong><span>{status(j)}</span><small>{j.completed_tick!==null?`Finished ${solOf(j.completed_tick)}`:j.started_tick!==null?`Started ${solOf(j.started_tick)}`:`${fmt(j.target)} ${j.unit} to do`}</small></button>)}</div>
   <article className="chapter-detail"><div className="chapter-main"><span className="eyebrow">02 / {status(job).toUpperCase()}</span><h2>{job.title}</h2>
    <div className="chapter-explanation"><section><h3>Basis</h3><p>{job.basis}</p></section><section><h3>Progress <Tag kind="modeled"/></h3><p>{fmt(job.done)} of {fmt(job.target)} {job.unit} ({fmt(job.progress*100)}%).</p></section></div>
    <div className="job-requirements"><span>Equipment: {job.assigned.length?job.assigned.map(a=>s.assets.find(x=>x.id===a)?.name).join(', '):`any ${job.asset_kinds.join('/')}`}</span><span>{job.dependencies.length?`After: ${job.dependencies.map(d=>s.jobs.find(x=>x.id===d)?.title).join(', ')}`:'No prerequisites'}</span></div>
    <button className="text-link" onClick={()=>select(job.id)}>Inspect work order, calculation and result <ArrowRight/></button></div>
   <aside className="chapter-reason"><span className="eyebrow">03 / THE DECISION</span><h3>{job.reason&&job.status!=='complete'?'What is holding it up?':decision?'Why it was authorized':'Not yet authorized'}</h3><p>{job.reason&&job.status!=='complete'?job.reason:decision?.summary||'No agent has proposed this work yet.'}</p>{decision&&<small>{decision.actor} · {decision.id} · {solOf(decision.tick)}</small>}{decision?.assurance&&<div className="assurance-box"><small><Tag kind="model"/> Assurance {decision.assurance.approved?'approved':'held'}: {decision.assurance.reason}</small>{decision.assurance.open_conditions.length>0&&<ul>{decision.assurance.open_conditions.map(c=><li key={c.id}><Tag kind="computed"/> Open condition (simulator): {c.text}</li>)}</ul>}</div>}<button className="text-link" onClick={()=>navigate('Agents')}>Meet the team <ArrowRight/></button></aside></article>
   <details className="chapter-citation"><summary><BookOpen/> 04 / Numbers behind this step <span>{params.length} parameters</span></summary>{params.map(({n,p})=><p key={n}><strong>{n}</strong>: {fmt(p.value,4)} {p.unit} · <Tag kind={paramTag(p.classification)}/> {p.classification}{p.source?` · ${s.spec.sources[p.source]?.title}, ${p.locator}`:''}{p.formula?` · ${p.formula}`:''}{p.quote&&<><br/><q>{p.quote}</q></>}</p>)}<button onClick={()=>navigate('Records')}>All parameters and decisions <ArrowRight/></button></details>
  </section>
  <div className="journey-results"><section className="journey-chart"><div className="journey-section-heading"><div><span className="eyebrow">SIMULATOR RESULTS</span><h2>Is the plan working?</h2></div><span>{job.title} · {job.unit}</span></div><ProgressChart s={s} data={data} job={job}/></section>
   <section className="mars-feed"><span className="eyebrow">RESOURCES & COST</span><h2>What it takes.</h2><p>{s.power_commissioned?`Power allocated: ${fmt(s.power_used_kw,2)} of ${fmt(s.power_capacity_kw)} kW.`:'Fission power not yet commissioned: no grid power.'} Energy used: {fmt(s.energy_used_kwh)} kWh{Object.keys(s.energy_unestimated_hours).length?` plus unpublished energy for ${Object.entries(s.energy_unestimated_hours).map(([k,h])=>`${k} (${fmt(h)} h)`).join(', ')}`:''}.</p><p>Operations: {usd(s.spent_usd)}. Landed capital: {usd(s.capital_usd)}{s.capital_unestimated.length?` + not estimated for ${s.capital_unestimated.join(', ')}`:''}.</p><p><Tag kind="assumed"/> Cost basis: Perseverance historical figures (decision D5). Not a commercial price.</p>{(s.orders||[]).length>0&&<div className="orders"><h3>Replacement robots (D12)</h3>{s.orders!.map(o=><p key={o.id}><b>{o.asset_name}</b> · {o.status} · launch {o.launch_utc.slice(0,10)}, arrival {o.arrival_utc.slice(0,10)} · {o.cost_usd===null?'cost not estimated':usd(o.cost_usd)} · ordered by {o.actor}</p>)}</div>}{s.assets.some(a=>!a.available)&&<p role="alert">Failed: {s.assets.filter(a=>!a.available).map(a=>a.name).join(', ')}.</p>}<p>Local ground instruments: <strong>uninstrumented</strong>.</p></section></div>
  <details className="collapsible"><summary>About this mission: what is real, what is simulated, legend</summary><HowItWorks snap={snap}/><Legend/></details>
 </div>;
}
