'use client';
// D17: landing at the mission site, replayed from NASA's published Mars 2020 timeline (parameters edl.*).
// Altitude/speed are shown as published at each event; between events they are interpolated and labelled so.
// Vehicle height on screen is a compressed (log) visual scale, not to scale.
import {Canvas,useFrame,useThree} from '@react-three/fiber';
import {Html,Line} from '@react-three/drei';
import {useEffect,useMemo,useRef,useState,Suspense} from 'react';
import * as THREE from 'three';
import {api,fmt} from '../lib/mission';
import {Ground,GroundBoundary,PlainGround,Model,FILE} from './MissionScene';

type Cite={parameter:string;value:number;unit:string;classification:string;quote:string|null;source:string|null;url:string|null;formula:string|null};
type Ev={key:string;title:string;t_s:number|null;altitude_m:number|null;speed_kph:number|null;evidence:Cite[];note:string|null};
type Payload={id:string;name:string;kind:string;position:[number,number,number]};
export type Landing={site:{name?:string;latitude:number;longitude_east:number};genesis_unix:number;
 edl:{reference:string;events:Ev[];conflict:{note:string}};payload:Payload[];decision:{choice:string}};


// Times for every event; the backshell time is not published, so it is placed where the interpolated altitude reaches its published altitude.
// A required published value that is missing stops the replay with its name; nothing is substituted.
function need(v:number|null|undefined,name:string):number{if(v==null)throw new Error(`Landing data missing ${name}`);return v;}
function timeline(t:Landing){
 const ev=t.edl.events.map(e=>({...e}));const by=(k:string)=>ev.find(e=>e.key===k)!;
 const chute=by('parachute'),crane=by('skycrane'),td=by('touchdown'),bs=by('backshell');
 const knots:[number,number][]=[[chute.t_s!,chute.altitude_m!],[crane.t_s!,crane.altitude_m!],[td.t_s!,0]];
 const alt=(x:number)=>{if(x<knots[0][0])return null;for(let i=0;i<knots.length-1;i++){const [t0,a0]=knots[i],[t1,a1]=knots[i+1];if(x<=t1)return a0+(a1-a0)*(x-t0)/(t1-t0);}return 0;};
 const [t0,a0]=knots[0],[t1,a1]=knots[1];bs.t_s=t0+(a0-bs.altitude_m!)*(t1-t0)/(a0-a1);
 const tBs=bs.t_s;
 return {ev,alt,start:by('cruise-separation').t_s!,entry:0,chute:chute.t_s!,shield:by('heat-shield').t_s!,backshell:tBs,crane:crane.t_s!,touchdown:td.t_s!,bridle:need(crane.evidence.find(c=>c.parameter==='edl.bridle_length_m')?.value,'edl.bridle_length_m')};
}
type TL=ReturnType<typeof timeline>;

// Visual height: log-compressed. Before the first published altitude the height is illustrative only.
const visY=(alt:number)=>2+28*Math.log10(1+alt/8);
function visualHeight(tl:TL,t:number){const a=tl.alt(t);if(a!=null)return visY(a);const top=visY(11000)+60;const f=Math.min(1,Math.max(0,(t-tl.start)/(tl.chute-tl.start)));return top-(top-visY(11000))*f;}

function Vehicle({tl,t}:{tl:TL;t:number}){
 const g=useRef<THREE.Group>(null);const y=visualHeight(tl,t);
 const plasma=t>=tl.entry&&t<tl.chute*0.75;const chute=t>=tl.chute&&t<tl.backshell;const shieldOn=t<tl.shield;const backshellOn=t<tl.backshell;
 const powered=t>=tl.backshell&&t<tl.touchdown+4;const crane=t>=tl.crane;const landed=t>=tl.touchdown;
 const cable=crane?Math.min(1,(t-tl.crane)/Math.max(1,tl.touchdown-tl.crane-4))*tl.bridle:0;
 const stageY=landed?y+Math.max(0,(t-tl.touchdown))*3:y+cable;
 useFrame(({clock})=>{if(g.current&&!landed){g.current.rotation.y=clock.elapsedTime*.2;}});
 return <>
  <group ref={g} position={[0,stageY,0]}>
   {t<tl.entry&&<mesh position={[0,1.6,0]}><cylinderGeometry args={[2.2,2.2,.6,24]}/><meshStandardMaterial color="#c7ccd1" metalness={.5}/></mesh>}
   {backshellOn&&<mesh position={[0,.6,0]}><coneGeometry args={[2,2.2,24,1,true]}/><meshStandardMaterial color="#e8e8e8" side={THREE.DoubleSide}/></mesh>}
   {shieldOn&&<mesh position={[0,-.6,0]} rotation={[Math.PI,0,0]}><coneGeometry args={[2.2,.7,24]}/><meshStandardMaterial color="#5b3a28"/></mesh>}
   {plasma&&<mesh position={[0,-1.2,0]}><sphereGeometry args={[3,24,16]}/><meshBasicMaterial color="#ff7a2a" transparent opacity={.35}/></mesh>}
   {chute&&<group position={[0,9,0]}><mesh><sphereGeometry args={[5,32,12,0,Math.PI*2,0,Math.PI/2.4]}/><meshStandardMaterial color="#f4f1ea" side={THREE.DoubleSide}/></mesh>
    {[0,1,2,3,4,5].map(i=>{const a=i/6*Math.PI*2;return <Line key={i} points={[[Math.cos(a)*4.2,1,Math.sin(a)*4.2],[0,-8,0]]} color="#ddd" lineWidth={1}/>;})}</group>}
   {powered&&<group><mesh><boxGeometry args={[3,.6,3]}/><meshStandardMaterial color="#b9b9b9" metalness={.6}/></mesh>
    {[[1.4,1.4],[-1.4,1.4],[1.4,-1.4],[-1.4,-1.4]].map(([x,z],i)=><mesh key={i} position={[x,-.8,z]} rotation={[Math.PI,0,0]}><coneGeometry args={[.25,1.2,12]}/><meshBasicMaterial color="#9fd4ff" transparent opacity={.8}/></mesh>)}</group>}
  </group>
  {t>=tl.backshell&&<group position={[0,landed?0:stageY-cable-.6,0]}><Suspense fallback={null}><Model file={FILE.rover[0]} size={FILE.rover[1]}/></Suspense>
   {crane&&!landed&&<Line points={[[0,1,0],[0,1+cable,0]]} color="#ddd" lineWidth={1}/>}</group>}
  {t>=tl.shield&&t<tl.shield+40&&<mesh position={[4,visualHeight(tl,tl.shield)-(t-tl.shield)*2,2]}><coneGeometry args={[2.2,.7,24]}/><meshStandardMaterial color="#5b3a28"/></mesh>}
  {landed&&t<tl.touchdown+20&&<Dust t={t-tl.touchdown}/>}
 </>;
}
function Dust({t}:{t:number}){const r=2+t*.8;return <mesh position={[0,.5,0]}><sphereGeometry args={[r,24,12,0,Math.PI*2,0,Math.PI/2]}/><meshBasicMaterial color="#c98a5e" transparent opacity={Math.max(0,.45-t*.022)}/></mesh>;}

function Cam({tl,t,at}:{tl:TL;t:number;at:[number,number,number]}){const {camera}=useThree();
 useFrame((_,dt)=>{const y=visualHeight(tl,Math.min(t,tl.touchdown));const low=y<16;const k=1-Math.exp(-dt*4);
  const target=new THREE.Vector3(at[0],low?Math.max(1.5,y*.6):y,at[2]);
  const pos=low?new THREE.Vector3(at[0]+18,8,at[2]+22):new THREE.Vector3(at[0]+22,y+5,at[2]+26);
  camera.position.lerp(pos,k);camera.lookAt(target);});return null;}

function Payloads({t,tl,items}:{t:number;tl:TL;items:Payload[]}){
 return <>{items.map((a,i)=>{const show=t>=tl.touchdown+3+i*1.2;if(!show||!FILE[a.kind])return null;
  return <group key={a.id} position={a.position}><Suspense fallback={null}><Model file={FILE[a.kind][0]} size={FILE[a.kind][1]}/></Suspense>
   <Html position={[0,FILE[a.kind][1]+1.2,0]} center><span className="scene-chip">{a.name.split(' (')[0]} · landed</span></Html></group>;})}</>;
}

export default function LandingSequence({mid,onExit,autoplay=false}:{mid:string;onExit:()=>void;autoplay?:boolean}){
 const [tr,setTr]=useState<Landing|null>(null);const [err,setErr]=useState<string|null>(null);
 const [t,setT]=useState(0);
 const [speed,setSpeed]=useState(6);const [playing,setPlaying]=useState(autoplay);// plays right after Start; as a replay it opens paused
 useEffect(()=>{api<Landing>(`missions/${mid}/landing`).then(setTr).catch(e=>setErr(String(e)));},[mid]);
 const built=useMemo(()=>{if(!tr)return {tl:null,err:null};try{return {tl:timeline(tr),err:null};}catch(e){return {tl:null,err:String(e)};}},[tr]);const tl=built.tl;
 useEffect(()=>{if(tl)setT(tl.start);},[tl]);
 useEffect(()=>{if(!tl||!playing)return;let last=performance.now(),raf=0;
  const step=(now:number)=>{const dt=(now-last)/1000;last=now;
   setT(x=>{const fast=x<tl.entry?Math.max(speed,60):speed;return Math.min(tl.touchdown+30,x+dt*fast);});
   raf=requestAnimationFrame(step);};raf=requestAnimationFrame(step);return()=>cancelAnimationFrame(raf);},[tl,playing,speed]);
 const fail=err||built.err||(tr&&!tr.payload.some(a=>a.kind==='rover')?'Landing data has no rover in the genesis payload':null);
 if(fail)return <section className="mission-scene"><p className="fallback">Landing replay unavailable: {fail}</p><button onClick={onExit}>Go to live outpost</button></section>;
 if(!tr||!tl)return <section className="mission-scene"><p>Loading landing data…</p></section>;
 const alt=tl.alt(t);const passed=tl.ev.filter(e=>e.t_s!=null&&t>=e.t_s);const cur=passed.at(-1);const lastSpeed=[...passed].reverse().find(e=>e.speed_kph!=null);
 const done=t>=tl.touchdown;
 // The skycrane sets the rover down at its genesis position; the other payload appears at theirs.
 const spot=tr.payload.find(a=>a.kind==='rover')!.position;
 const clock=t<0?`E−${fmt(-t,0)} s`:`E+${fmt(t,0)} s`;
 return <section className="mission-scene landing">
  <div className="scene-canvas">
   <Canvas shadows camera={{position:[30,120,34],fov:50}} dpr={[1,1.6]}>
    <color attach="background" args={[t<tl.entry?'#05070c':'#c99a74']}/>
    <ambientLight intensity={.55}/><directionalLight position={[40,80,20]} intensity={2.2} castShadow/>
    <fog attach="fog" args={['#cf9f7c',120,520]}/>
    <GroundBoundary><Suspense fallback={<PlainGround/>}><Ground/></Suspense></GroundBoundary>
    <group position={[spot[0],0,spot[2]]}><Vehicle tl={tl} t={t}/></group><Payloads t={t} tl={tl} items={tr.payload.filter(a=>a.kind!=='rover')}/><Cam tl={tl} t={t} at={spot}/>
   </Canvas>
  </div>
  <div className="scene-hud">
   <div className="hud-block"><small>ENTRY, DESCENT &amp; LANDING</small><strong>{done?'Landed':cur?.title??'Before cruise stage separation'}</strong>
    <span>Arcadia Planitia site (scenario) · {fmt(tr.site.latitude,2)}°N {fmt(tr.site.longitude_east,2)}°E</span>
    <span>{clock} (E = atmospheric entry)</span></div>
   <div className="hud-block"><small>ALTITUDE · SPEED</small>
    <span>Altitude: {alt==null?'not published before parachute deploy':`${cur&&cur.altitude_m!=null&&Math.abs(alt-cur.altitude_m)<1?'':'≈ '}${fmt(alt,0)} m${cur&&cur.altitude_m!=null&&Math.abs(alt-cur.altitude_m)<1?' (published)':' (interpolated)'}`}</span>
    <span>Speed: {lastSpeed?(lastSpeed===cur?`${fmt(lastSpeed.speed_kph!,1)} km/h (published)`:`not published here · last published ${fmt(lastSpeed.speed_kph!,1)} km/h at ${lastSpeed.title.toLowerCase()}`):'not published for this phase'}</span></div>
   <div className="hud-block landing-events"><small>EVENTS · NASA MARS 2020 TIMELINE</small>
    {tl.ev.map(e=>{const on=e.t_s!=null&&t>=e.t_s;const c=e.evidence[0];
     return <span key={e.key} className={on?'ev on':'ev'} title={e.evidence.map(x=>`${x.parameter}: “${x.quote||x.formula}”`).join('\n')}>{on?'●':'○'} {e.title}{e.t_s!=null?` · E${e.t_s<0?'−':'+'}${fmt(Math.abs(e.t_s),0)} s`:''}{e.key==='backshell'?' (time interpolated)':''}{c?.url&&<> · <a href={c.url} target="_blank" rel="noreferrer">source</a></>}</span>;})}</div>
   <div className="hud-block replay"><small>CONTROLS</small>
    <div><button className="play" onClick={()=>setPlaying(p=>!p)}>{playing?'❚❚ Pause':'▶ Play'}</button><button onClick={()=>{setPlaying(false);setT(tl.start);}}>■ Stop</button>
     {[1,6,30].map(x=><button key={x} onClick={()=>setSpeed(x)} aria-pressed={speed===x} className={speed===x?'on':''}>{x===1?'Real time':`${x}×`}</button>)}</div>
    <div><button onClick={()=>{setSpeed(1);setT(tl.crane-6);}}>Skip to skycrane</button><button onClick={onExit}>Go to live outpost</button></div></div>
  </div>
  <p className="scene-note">Landing replayed from published values (decision D17), not simulated as physics. Timeline: NASA/JPL Mars 2020 EDL captions; the outpost’s own cargo landers are not specified by any source, so each payload uses this reference profile. Heat-shield timing conflict: {tr.edl.conflict.note} Vehicle height on screen is compressed, not to scale; values between published events are interpolated and labelled.</p>
 </section>;
}
