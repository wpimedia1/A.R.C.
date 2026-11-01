'use client';
import {useEffect,useState} from 'react';
import {api,solOf,HIRISE_HERO} from '../lib/mission';
import {Tag} from './Explain';
export type Visual={trigger:string;created_at:number;has_image:boolean;status:string;prompt:string;sol:number;tick:number;revision:number;method:string;model:string;label:string;receipt_id:string;error?:string;response_headers?:Record<string,string>;sha256?:string};
export type VisualSet={visuals:Visual[];site_analysis:{failed_at:number;error:string}|null};
export function useVisuals(mid:string,revision:number){const [data,setData]=useState<VisualSet|null>(null);useEffect(()=>{let live=true;api<VisualSet>(`missions/${mid}/visuals`).then(v=>{if(live)setData(v);}).catch(()=>{if(live)setData(null);});return()=>{live=false;};},[mid,revision]);return data;}
const src=(mid:string,v:Visual)=>`/api/v1/missions/${mid}/visuals/${encodeURIComponent(v.trigger)}/image`;
const title=(v:Visual)=>v.trigger==='genesis'?'Genesis':v.trigger.replace('job:','')+' complete';
export function HeroVisual({set,mode}:{mid:string;set:VisualSet|null;mode:string}){
 // The main picture is always a real photograph. Generated art never stands in for observation (audit 2026-10-31).
 const failed=set?.visuals.filter(v=>v.status==='failed').at(-1);const made=set?.visuals.filter(v=>v.has_image).length||0;
 return <figure className="hero-visual"><img src={HIRISE_HERO.local} alt="HiRISE orbital photograph of Arcadia Planitia (candidate Red Dragon landing site)" onError={e=>{const i=e.currentTarget;const chain=[HIRISE_HERO.src,HIRISE_HERO.fallback];const n=chain.findIndex(u=>u===i.src);if(n<chain.length-1)i.src=chain[n+1];}}/>
  <figcaption><strong><Tag kind="measured"/> Arcadia Planitia from orbit · real photograph</strong><span>HiRISE ESP_052358_2210 at 40.7° N, 201.6° E, {HIRISE_HERO.credit}. About 524 km from the scenario site (40° N, 190° E): regional context, not the work site.</span>
  <span className={failed?'hero-alert':''}>{failed?`Muse Image illustration failed: ${failed.error}`:mode==='meta'?(made?`${made} AI illustration${made>1?'s':''} of the simulated outpost below (stamped, not evidence).`:'AI illustrations of the simulated outpost appear below when generated.'):'Benchmark mode: no Muse Image illustrations are generated.'}</span></figcaption></figure>;
}
export function VisualTimeline({mid,set}:{mid:string;set:VisualSet|null}){
 if(!set?.visuals.length)return null;
 return <section className="visual-timeline"><span className="eyebrow">MUSE IMAGE · ARTIST'S IMPRESSION</span><h2>Artist’s impression of the simulated outpost.</h2><p><Tag kind="generated"/> Drawn by muse-image-1.0 from the simulation record, each frame edited from the previous one. The label is stamped into every image. These pictures show simulated state: not photographs, not evidence that any equipment exists or any work happened.</p><div className="visual-strip">{set.visuals.map(v=><figure key={v.trigger} className={v.status}>{v.has_image?<img src={src(mid,v)} alt={title(v)} loading="lazy"/>:<div className="visual-failed">{v.error}</div>}<figcaption><strong>{title(v)}</strong><span>{solOf(v.tick)}</span></figcaption></figure>)}</div></section>;
}
