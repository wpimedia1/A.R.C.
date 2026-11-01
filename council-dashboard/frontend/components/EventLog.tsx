'use client';
import {useEffect,useState} from 'react';
import {api} from '../lib/mission';
type Row={at:number;source:string;kind:string;record:Record<string,unknown>};
const summary=(r:Row)=>{const x=r.record as Record<string,any>;
 if(r.source==='revision')return `revision ${x.revision} · ${x.operation?.kind||'change'} · tick ${x.tick}`;
 if(r.source==='receipt')return `${x.model||''} ${x.operation||x.receipt_id||''} · ${r.kind}${x.http_status?` · HTTP ${x.http_status}`:''}${x.response_id?` · ${x.response_id}`:''}`;
 if(r.kind==='dsn')return x.error?`DSN unreadable: ${String(x.error).slice(0,140)}`:`DSN read: ${x.dishes_in_feed??'?'} dishes, ${(x.targets_seen as unknown[]|undefined)?.length??'?'} targets, Mars spacecraft ${(x.mars_spacecraft as string[]|undefined)?.join(', ')||'none'}`;
 if(x.error)return `${r.kind}: ${String(x.error).slice(0,160)}`;
 return `${r.kind}`;};
export default function EventLog({mid}:{mid:string}){
 const [rows,setRows]=useState<Row[]>([]);const [next,setNext]=useState<number|null>(null);const [error,setError]=useState('');const [source,setSource]=useState('');
 const load=(after?:number|null,reset=false)=>api<{rows:Row[];next_after:number|null}>(`missions/${mid}/log?limit=200${after?`&after=${after}`:''}${source?`&source=${source}`:''}`).then(d=>{setRows(r=>reset?d.rows:[...r,...d.rows]);setNext(d.next_after);setError('');}).catch(e=>setError(e.message));
 useEffect(()=>{load(null,true);},[mid,source]);// eslint-disable-line react-hooks/exhaustive-deps
 return <section className="event-log"><h2>Complete history from genesis</h2><p>Every mission revision, model request change, live reading status and worker event, append-only and in time order.</p>
  <label>Show <select value={source} onChange={e=>setSource(e.target.value)}><option value="">everything</option><option value="revision">mission revisions</option><option value="receipt">model requests</option><option value="status">service and live-data status</option><option value="worker">worker</option></select></label>
  {error&&<p role="alert">{error}</p>}
  <ol>{rows.map((r,i)=><li key={i}><time>{new Date(r.at*1000).toLocaleString()}</time><b>{r.source}</b><span>{summary(r)}</span></li>)}</ol>
  {next&&<button onClick={()=>load(next)}>Load more</button>}{!rows.length&&!error&&<p>No records yet.</p>}</section>;
}
