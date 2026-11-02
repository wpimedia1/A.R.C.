'use client';
import {useEffect,useState} from 'react';
import {api,solOf} from '../lib/mission';
import {Tag} from './Explain';
export type Visual={trigger:string;created_at:number;has_image:boolean;status:string;prompt:string;sol:number;tick:number;revision:number;method:string;model:string;label:string;receipt_id:string;error?:string;response_headers?:Record<string,string>;sha256?:string};
export type VisualSet={visuals:Visual[];site_analysis:{failed_at:number;error:string}|null};
export function useVisuals(mid:string,revision:number){const [data,setData]=useState<VisualSet|null>(null);useEffect(()=>{let live=true;api<VisualSet>(`missions/${mid}/visuals`).then(v=>{if(live)setData(v);}).catch(()=>{if(live)setData(null);});return()=>{live=false;};},[mid,revision]);return data;}
const src=(mid:string,v:Visual)=>`/api/v1/missions/${mid}/visuals/${encodeURIComponent(v.trigger)}/image`;
const title=(v:Visual)=>v.trigger==='genesis'?'Genesis':v.trigger.replace('job:','')+' complete';
export function VisualTimeline({mid,set}:{mid:string;set:VisualSet|null}){
 if(!set?.visuals.length)return null;
 return <section className="visual-timeline"><span className="eyebrow">MUSE IMAGE · ARTIST'S IMPRESSION</span><h2>Artist’s impression of the simulated outpost.</h2><p><Tag kind="generated"/> Drawn by muse-image-1.0 from the simulation record, each frame edited from the previous one. The label is stamped into every image. These pictures show simulated state: not photographs, not evidence that any equipment exists or any work happened.</p><div className="visual-strip">{set.visuals.map(v=><figure key={v.trigger} className={v.status}>{v.has_image?<img src={src(mid,v)} alt={title(v)} loading="lazy"/>:<div className="visual-failed">{v.error}</div>}<figcaption><strong>{title(v)}</strong><span>{solOf(v.tick)}</span></figcaption></figure>)}</div></section>;
}
