'use client';
import {useState} from 'react';
export type DailyObservation={sol:number;observed_at:string;source_row:number;air_min_c:number|null;air_max_c:number|null;ground_min_c:number|null;ground_max_c:number|null;pressure_pa:number|null;uv_category:string|null;quality:string;missing_fields:string[]};
export type WeatherEvidence={daily_observations?:DailyObservation[];archive_record_count?:number;version_id:string;content_hash:string;url?:string;observation_time?:string;retrieved_at?:number;use?:string};
const metrics=[['air_min_c','Minimum air temperature','°C'],['air_max_c','Maximum air temperature','°C'],['ground_min_c','Minimum ground temperature','°C'],['ground_max_c','Maximum ground temperature','°C'],['pressure_pa','Atmospheric pressure','Pa']] as const;
export default function WeatherHistory({source}:{source:WeatherEvidence}){
 const rows=source.daily_observations||[];
 const [metric,setMetric]=useState<(typeof metrics)[number]>(metrics[1]);
 const [selected,setSelected]=useState<number|null>(null);
 if(!rows.length)return null;
 const point=rows.find(r=>r.sol===selected)||rows.at(-1)!;
 const valid=rows.filter(r=>r[metric[0]]!==null);
 const values=valid.map(r=>r[metric[0]] as number),min=Math.min(...values),max=Math.max(...values);
 const x=(sol:number)=>45+(sol-rows[0].sol)/Math.max(1,rows.at(-1)!.sol-rows[0].sol)*820;
 const y=(v:number)=>190-(v-min)/Math.max(1,max-min)*150;
 const age=source.observation_time?Math.max(0,Math.floor((Date.now()-Date.parse(source.observation_time))/86400000)):null;
 return <section className="weather-panel daily-weather"><div><span className="eyebrow">CURIOSITY / GALE CRATER</span><h2>Mars weather, one observed sol at a time.</h2><p>{source.archive_record_count?.toLocaleString()} published daily records. Showing {rows.length} available sols, {rows[0].observed_at} to {rows.at(-1)!.observed_at}.</p><p><strong>Latest observation: {age} Earth days old.</strong> Retrieval time does not change observation age.</p><label>Measurement <select value={metric[0]} onChange={e=>setMetric(metrics.find(m=>m[0]===e.target.value)!)}>{metrics.map(m=><option key={m[0]} value={m[0]}>{m[1]} ({m[2]})</option>)}</select></label></div>
 {valid.length?<figure><svg viewBox="0 0 900 230" role="img" aria-label={`${metric[1]} from ${rows[0].observed_at} to ${rows.at(-1)!.observed_at}. Select a sol below for exact measurements.`}>
 {[min,(min+max)/2,max].map((v,i)=><g key={i}><line x1="45" x2="865" y1={y(v)} y2={y(v)} stroke="#d4dbd6"/><text x="0" y={y(v)+4} fontSize="12" fill="#42564a">{v.toFixed(0)}</text></g>)}
 {valid.map((r,i)=>{const prev=valid[i-1];return <g key={r.sol}>{prev&&r.sol-prev.sol===1&&<line x1={x(prev.sol)} y1={y(prev[metric[0]]!)} x2={x(r.sol)} y2={y(r[metric[0]]!)} stroke="#ad4f2c" strokeWidth="2"/>}<circle cx={x(r.sol)} cy={y(r[metric[0]]!)} r={point.sol===r.sol?5:2.5} fill={point.sol===r.sol?'#172f26':'#ad4f2c'}><title>Sol {r.sol} · {r.observed_at} · {r[metric[0]]} {metric[2]}</title></circle></g>})}
 <text x="45" y="220" fontSize="12" fill="#42564a">Sol {rows[0].sol}</text><text x="790" y="220" fontSize="12" fill="#42564a">Sol {rows.at(-1)!.sol}</text></svg><figcaption>{metric[1]} ({metric[2]}). Gaps remain gaps; missing measurements are not interpolated.</figcaption></figure>:<p>No valid measurements for this variable in the selected window.</p>}
 <div><label>Inspect observation <select value={point.sol} onChange={e=>setSelected(Number(e.target.value))}>{rows.slice().reverse().map(r=><option key={r.sol} value={r.sol}>Sol {r.sol} · {r.observed_at}</option>)}</select></label><div className="compare-grid">{metrics.map(m=><div key={m[0]}><small>{m[1]}</small><strong>{point[m[0]]===null?'Unavailable':`${point[m[0]]} ${m[2]}`}</strong></div>)}</div><p>UV category: {point.uv_category||'Unavailable'}. {point.quality}.</p><p>{source.use}</p><details><summary>Trace this observation to its source</summary><p>Source array row {point.source_row}, sol {point.sol}. Transformation: weather-daily-1. Units normalized; no missing values filled.</p><p>Pinned version: <code>{source.version_id}</code></p><p>Source SHA-256: <code>{source.content_hash}</code></p><a href={source.url} target="_blank" rel="noreferrer">Open NASA source feed ↗</a><p>The upstream feed can change; this mission retains the pinned version above.</p></details></div></section>;
}
