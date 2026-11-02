'use client';
// The mission, live: robots move when their work is running, wait visibly when it is not,
// work orders fly Earth -> relay orbiter -> outpost, and the sun sits where it really is over the site right now.
// Motion is a visualization of the simulated job state (progress, assignments); models are illustrative stand-ins.
import {Canvas,useFrame,useLoader} from '@react-three/fiber';
import {OrbitControls,Html,useGLTF,Line} from '@react-three/drei';
import {useMemo,useRef,useState,useEffect,Suspense,Component,ReactNode} from 'react';
import * as THREE from 'three';
import {State,Asset,Job,Snapshot,api,solOf,fmt} from '../lib/mission';
import LiveStrip from './LiveStrip';

class Boundary extends Component<{children:ReactNode},{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return {failed:true};}render(){return this.state.failed?<p className="fallback">3D view unavailable in this browser.</p>:this.props.children;}}

export function Model({file,size,tint}:{file:string;size:number;tint?:string|null}){
 const {scene}=useGLTF(file,'/draco/');
 const obj=useMemo(()=>{const c=scene.clone(true),b=new THREE.Box3().setFromObject(c),d=b.getSize(new THREE.Vector3()),ctr=b.getCenter(new THREE.Vector3()),k=size/Math.max(d.x,d.y,d.z);
  c.scale.setScalar(k);c.position.set(-ctr.x*k,-b.min.y*k,-ctr.z*k);
  c.traverse(o=>{if(o instanceof THREE.Mesh){o.castShadow=true;o.receiveShadow=true;if(tint){const l=Array.isArray(o.material)?o.material:[o.material];o.material=l.map(m=>{const x=(m as THREE.MeshStandardMaterial).clone();x.color=new THREE.Color(tint);return x;});}}});return c;},[scene,size,tint]);
 return <primitive object={obj}/>;
}
export const FILE:Record<string,[string,number]>={rover:['/models/perseverance.glb',2.4],excavator:['/models/kenney/rover.glb',1.5],rodwell:['/models/kenney/machine_barrelLarge.glb',1.8],power:['/models/kenney/machine_generatorLarge.glb',3],habitat:['/models/kenney/hangar_roundB.glb',5.5]};

const jobOf=(s:State,a:Asset)=>s.jobs.find(j=>j.assigned.includes(a.id));
// A work order is in flight only once it has been sent with a known arrival step; before that it waits on Earth.
const sent=(j:Job)=>j.status==='uplink'&&j.uplink?.sent_tick!=null&&j.uplink?.arrival_tick!=null;
const held=(j:Job)=>j.status==='uplink'&&!sent(j);
const heldText=(j:Job)=>j.uplink?.assurance==='pending'?'Awaiting assurance review on Earth':`Approved · waiting for DSN uplink to Mars${j.reason?` (${j.reason})`:''}`;
const standby=(s:State,a:Asset)=>((a as unknown as {standby_until_tick?:number}).standby_until_tick||0)>s.tick;

export function Ground(){
 const tex=useLoader(THREE.TextureLoader,'/api/v1/site/ground.jpg');
 useMemo(()=>{tex.wrapS=tex.wrapT=THREE.RepeatWrapping;tex.repeat.set(16,16);tex.colorSpace=THREE.SRGBColorSpace;tex.anisotropy=8;},[tex]);
 // HiRISE RED is a single band; multiplying by a regolith colour gives the familiar ochre without inventing detail.
 return <mesh rotation={[-Math.PI/2,0,0]} receiveShadow><planeGeometry args={[1600,1600]}/><meshStandardMaterial map={tex} color="#d08a5c" roughness={1}/></mesh>;
}
export class GroundBoundary extends Component<{children:ReactNode},{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return {failed:true};}render(){return this.state.failed?<PlainGround/>:this.props.children;}}
export function PlainGround(){return <mesh rotation={[-Math.PI/2,0,0]} receiveShadow><planeGeometry args={[1600,1600]}/><meshStandardMaterial color="#b9734a" roughness={1}/></mesh>;}

// Survey: the rover drives the simulated survey distance, east from its start (the route planner's west-to-east
// convention, D13). Its position is the metres driven in the simulation (job.done), not an animation.
const surveyJobs=(s:State)=>s.jobs.filter(j=>j.kind==='survey');
function Rover({a,s}:{a:Asset;s:State}){
 const ref=useRef<THREE.Group>(null);const j=jobOf(s,a);const moving=a.available&&j?.status==='running'&&j.kind==='survey'&&!standby(s,a);
 const driven=surveyJobs(s).reduce((t,x)=>t+x.done,0);
 const at=new THREE.Vector3(a.position[0]+driven,0,a.position[2]);
 useFrame((_,dt)=>{if(ref.current)ref.current.position.lerp(at,1-Math.exp(-dt*2));});
 return <group ref={ref} position={a.position} rotation={[0,Math.PI/2,0]}><Suspense fallback={null}><Model file={FILE.rover[0]} size={FILE.rover[1]} tint={a.available?null:'#7a2c12'}/></Suspense>{moving&&<Dust/>}</group>;
}
function SurveyLine({a,s}:{a:Asset;s:State}){
 const jobs=surveyJobs(s);if(!jobs.length)return null;
 const planned=jobs.reduce((t,x)=>t+x.target,0),driven=jobs.reduce((t,x)=>t+x.done,0);const main=jobs.find(x=>x.id==='survey');
 const y=.08,x0=a.position[0],z=a.position[2];
 const route=(main as unknown as {route?:{detour_factor:number;base_target:number}}|undefined)?.route;
 const label=`Survey drive ${fmt(driven,1)} / ${fmt(planned,2)} m`+(route?` · hazard detour ×${route.detour_factor} applied (SAM, D13)`:' · no hazard detour applied');
 return <><Line points={[[x0,y,z],[x0+planned,y,z]]} color="#f4e3c8" lineWidth={1.5} dashed dashSize={1.2} gapSize={.8}/>
  {driven>0&&<Line points={[[x0,y+.01,z],[x0+driven,y+.01,z]]} color="#ffd27a" lineWidth={3}/>}
  <Html position={[x0+planned,1.2,z]} center><span className="scene-chip">{label}</span></Html></>;
}
function Dust(){const ref=useRef<THREE.Points>(null);const geo=useMemo(()=>{const g=new THREE.BufferGeometry();const p=new Float32Array(90);for(let i=0;i<90;i++)p[i]=(Math.random()-.5)*1.6;g.setAttribute('position',new THREE.BufferAttribute(p,3));return g;},[]);
 useFrame(({clock})=>{if(ref.current){ref.current.rotation.y=clock.elapsedTime;ref.current.position.y=.4+Math.sin(clock.elapsedTime*3)*.1;}});
 return <points ref={ref} geometry={geo} position={[0,.4,-1.4]}><pointsMaterial size={.12} color="#d9a27a" transparent opacity={.6}/></points>;}

// Trench and habitat sizes come from the environment package; the trench sits at the trench job's layout position.
const P=(s:State,name:string)=>s.spec.parameters[name].value;
const trenchAt=(s:State)=>{const t=s.jobs.find(j=>j.id==='trench')!;return new THREE.Vector3(...t.position);};
const SPOIL=new THREE.Vector3(11,0,16);// spoil pile: illustrative placement
function Excavator({a,s,i}:{a:Asset;s:State;i:number}){
 const ref=useRef<THREE.Group>(null);const j=jobOf(s,a);const moving=a.available&&j?.status==='running'&&!standby(s,a);
 const hab=s.assets.find(x=>x.kind==='habitat');const TRENCH=trenchAt(s);
 const target=j?.id==='shielding'&&hab?new THREE.Vector3(...hab.position):SPOIL;const home=new THREE.Vector3(...a.position);
 useFrame(({clock})=>{if(!ref.current)return;if(moving){const f=(Math.sin(clock.elapsedTime*0.6+i*1.7)+1)/2;const p=TRENCH.clone().add(new THREE.Vector3(i*2-1,0,0)).lerp(target,f);ref.current.position.lerp(p,0.1);ref.current.rotation.y=Math.atan2(target.x-TRENCH.x,target.z-TRENCH.z)+(Math.cos(clock.elapsedTime*0.6+i*1.7)>0?0:Math.PI);}else ref.current.position.lerp(home,0.05);});
 return <group ref={ref} position={a.position}><Suspense fallback={null}><Model file={FILE.excavator[0]} size={FILE.excavator[1]} tint={a.available?null:'#7a2c12'}/></Suspense></group>;
}
function Drill({a,s}:{a:Asset;s:State}){
 const ref=useRef<THREE.Group>(null);const d=s.jobs.find(j=>j.id==='drill');const w=s.jobs.find(j=>j.id==='water');
 const spinning=a.available&&(d?.status==='running'||w?.status==='running')&&!standby(s,a);
 useFrame((_,dt)=>{if(ref.current&&spinning)ref.current.rotation.y+=dt*1.6;});
 const level=w?w.progress:0;
 return <group position={a.position}><group ref={ref}><Suspense fallback={null}><Model file={FILE.rodwell[0]} size={FILE.rodwell[1]} tint={a.available?null:'#7a2c12'}/></Suspense></group>
  <mesh position={[2.2,.9,0]} castShadow><cylinderGeometry args={[.7,.7,1.8,24]}/><meshStandardMaterial color="#c9d1d4" transparent opacity={.45}/></mesh>
  {level>0&&<mesh position={[2.2,level*.9,0]}><cylinderGeometry args={[.66,.66,level*1.8,24]}/><meshStandardMaterial color="#4da3d4"/></mesh>}</group>;
}
function Power({a,s}:{a:Asset;s:State}){
 const ring=useRef<THREE.Mesh>(null);const j=s.jobs.find(x=>x.id==='power');const deploying=j?.status==='running';
 useFrame(({clock})=>{if(ring.current){ring.current.rotation.z=clock.elapsedTime*.8;(ring.current.material as THREE.MeshBasicMaterial).opacity=.35+.25*Math.sin(clock.elapsedTime*3);}});
 const hab=s.assets.find(x=>x.kind==='habitat');
 return <><group position={a.position}><Suspense fallback={null}><Model file={FILE.power[0]} size={FILE.power[1]}/></Suspense>
  {deploying&&<mesh ref={ring} rotation={[-Math.PI/2,0,0]} position={[0,.05,0]}><ringGeometry args={[2.6,2.9,48,1,0,Math.PI*2*(j?.progress||0)]}/><meshBasicMaterial color="#ffb347" transparent side={THREE.DoubleSide}/></mesh>}
  {s.power_commissioned&&<pointLight position={[0,3.4,0]} color="#ffcf7a" intensity={8} distance={10}/>}</group>
  {s.power_commissioned&&hab&&<Line points={[a.position,[a.position[0]/2+hab.position[0]/2,.05,a.position[2]/2+hab.position[2]/2],hab.position].map(p=>[p[0],.06,p[2]] as [number,number,number])} color="#ffcf7a" lineWidth={2}/>}</>;
}
function Site({s}:{s:State}){
 const tr=s.jobs.find(j=>j.id==='trench'),sh=s.jobs.find(j=>j.id==='shielding');const hab=s.assets.find(a=>a.kind==='habitat');
 const T=trenchAt(s);const depth=P(s,'habitat.trench_depth_m')*(tr?.progress||0);const spoil=(tr?.progress||0)-(sh?.progress||0)*0.9;
 return <>{depth>0.01&&<mesh position={[T.x,-depth/2+.01,T.z]}><boxGeometry args={[P(s,'habitat.diameter_m'),depth,P(s,'habitat.length_m')]}/><meshStandardMaterial color="#5a3424" roughness={1}/></mesh>}
  {spoil>0.01&&<mesh position={[SPOIL.x,0,SPOIL.z]} castShadow><coneGeometry args={[2.5+3*spoil,3*spoil,24]}/><meshStandardMaterial color="#a05a35" roughness={1}/></mesh>}
  {hab&&<group position={hab.position}><Suspense fallback={null}><Model file={FILE.habitat[0]} size={FILE.habitat[1]}/></Suspense>
   {(sh?.progress||0)>0&&<mesh scale={[1,(sh?.progress||0),1]} castShadow><sphereGeometry args={[P(s,'habitat.diameter_m')/2,32,16,0,Math.PI*2,0,Math.PI/2]}/><meshStandardMaterial color="#9a5634" roughness={1}/></mesh>}</group>}</>;
}
// A work order in flight: Earth (towards the sky) -> relay orbiter -> outpost, with its expected arrival.
function Packet({to,label}:{to:[number,number,number];label:string}){
 const ref=useRef<THREE.Mesh>(null);const from=new THREE.Vector3(-60,70,-60),via=new THREE.Vector3(0,38,40),dest=new THREE.Vector3(to[0],1.5,to[2]);
 useFrame(({clock})=>{if(!ref.current)return;const f=(clock.elapsedTime*.18)%1;const p=f<.6?from.clone().lerp(via,f/.6):via.clone().lerp(dest,(f-.6)/.4);ref.current.position.copy(p);});
 return <><Line points={[from,via,dest]} color="#7fd1ff" lineWidth={1.5} dashed dashSize={2} gapSize={1.5}/><mesh ref={ref}><sphereGeometry args={[.6,16,16]}/><meshBasicMaterial color="#7fd1ff"/></mesh>
  <Html position={[dest.x,dest.y+3.2,dest.z]} center><span className="scene-chip order">{label}</span></Html></>;
}
function Tags({s,at}:{s:State;at:(t:number)=>string}){
 return <>{s.assets.map(a=>{const j=jobOf(s,a);const sb=standby(s,a);
  const txt=!a.available?'FAILED':sb?`Standby: ${(a as unknown as {standby?:{reason:string}}).standby?.reason??'reason not recorded'}`:j?.status==='running'?`${j.title} · ${fmt(j.progress*100,0)}%`:j&&sent(j)?`Order in flight · arrives ${at(j.uplink!.arrival_tick!)}`:j&&held(j)?'Order approved · waiting for DSN uplink':'Idle';
  const cls=!a.available?'failed':sb?'standby':j?.status==='running'?'working':j&&sent(j)?'waiting':j&&held(j)?'held':'idle';
  const dx=a.kind==='rover'?surveyJobs(s).reduce((t,x)=>t+x.done,0):0;// the rover's tag follows the distance it has driven
  return <Html key={a.id} position={[a.position[0]+dx,(FILE[a.kind]?.[1]||2)+1.4,a.position[2]]} center><span className={'scene-tag '+cls}><b>{a.name.split(' (')[0]}</b>{txt}</span></Html>;})}</>;
}
function Scene({s,at,labels}:{s:State;at:(t:number)=>string;labels:boolean}){
 const sun=s.environment?.clock.site_sun_enu??null;// no sun direction recorded -> neutral light, no invented sun
 const sunPos:[number,number,number]|null=sun?[sun[0]*80,sun[2]*80,-sun[1]*80]:null;
 // Brightness follows the real solar elevation continuously (twilight before sunrise and after sunset), instead of a
 // day/night switch. The shading curve is a display mapping, not a measured sky brightness.
 const elev=sun?Math.asin(Math.max(-1,Math.min(1,sun[2])))*180/Math.PI:null;
 const ease=(a:number,b:number,x:number)=>{const t=Math.max(0,Math.min(1,(x-a)/(b-a)));return t*t*(3-2*t);};
 const k=elev==null?1:ease(-12,6,elev),direct=elev==null?0:ease(-1,6,elev);
 const mix=(n:string,d:string)=>'#'+new THREE.Color(n).lerp(new THREE.Color(d),k).getHexString();
 const flying=s.jobs.filter(sent);
 return <>
  <color attach="background" args={[mix('#140d0b','#d7a77f')]}/>{/* Mars daytime sky: butterscotch from suspended dust */}
  <ambientLight intensity={0.08+0.37*k}/><hemisphereLight args={['#f1c9a4','#3a2418',0.08+0.52*k]}/>
  {sunPos?<directionalLight position={sunPos} intensity={0.05+2.55*direct} castShadow shadow-mapSize={[2048,2048]} shadow-camera-left={-40} shadow-camera-right={40} shadow-camera-top={40} shadow-camera-bottom={-40}/>:<ambientLight intensity={0.5}/>}
  <fog attach="fog" args={[mix('#120c0a','#d6a98a'),120,420]}/>
  <GroundBoundary><Suspense fallback={<PlainGround/>}><Ground/></Suspense></GroundBoundary>
  <Site s={s}/>
  {s.assets.filter(a=>a.kind==='rover').map(a=><SurveyLine key={'line-'+a.id} a={a} s={s}/>)}
  {s.assets.map((a,i)=>a.kind==='rover'?<Rover key={a.id} a={a} s={s}/>:a.kind==='excavator'?<Excavator key={a.id} a={a} s={s} i={i}/>:a.kind==='rodwell'?<Drill key={a.id} a={a} s={s}/>:a.kind==='power'?<Power key={a.id} a={a} s={s}/>:null)}
  {flying.map(j=>{const a=s.assets.find(x=>j.assigned.includes(x.id));return a?<Packet key={j.id} to={a.position} label={`${j.title.split(' ').slice(0,3).join(' ')} → arrives ${at(j.uplink!.arrival_tick!)}`}/>:null;})}
  {labels&&<Tags s={s} at={at}/>}
 </>;
}

type Rev={revision:number;at:number;kind:string};
export default function MissionScene({snap,mid}:{snap:Snapshot;mid:string}){
 const [labels,setLabels]=useState(false);useEffect(()=>{const t=setTimeout(()=>setLabels(true),400);return()=>clearTimeout(t);},[]);
 const [revs,setRevs]=useState<Rev[]>([]);const [replay,setReplay]=useState<{n:number;state:State}|null>(null);const [playing,setPlaying]=useState(false);
 useEffect(()=>{api<{revisions:Rev[]}>(`missions/${mid}/revisions`).then(d=>setRevs(d.revisions)).catch(()=>{});},[mid,snap.revision]);
 const load=(n:number)=>api<{revision:number;state:State}>(`missions/${mid}/revisions/${n}`).then(d=>setReplay({n:d.revision,state:d.state}));
 useEffect(()=>{if(!playing||!revs.length)return;const id=setInterval(()=>{setReplay(r=>{const cur=r?.n||revs[0].revision;const next=revs.find(x=>x.revision>cur);if(!next){setPlaying(false);return r;}load(next.revision);return r;});},700);return()=>clearInterval(id);},[playing,revs]);// eslint-disable-line react-hooks/exhaustive-deps
 const s=replay?.state||snap.state;
 const spt=snap.seconds_per_tick;
 // Clock time of a future step, from the server's next-step time and step length only; unknown if either is missing.
 const at=(tick:number)=>{if(replay)return `step ${tick}`;if(snap.next_tick_at==null||spt==null)return 'time unknown';const base=snap.next_tick_at+(tick-s.tick-1)*spt;return new Date(base*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});};
 const running=s.jobs.filter(j=>j.status==='running');const flying=s.jobs.filter(sent);const waiting=s.jobs.filter(held);
 const c=s.environment?.clock;
 // Opening view frames the outpost and the rover's current point on its survey line (camera only; set once per visit).
 const [view]=useState(()=>{const rover=s.assets.find(a=>a.kind==='rover');const rx=rover?rover.position[0]+surveyJobs(s).reduce((t,x)=>t+x.done,0):0;
  const xs=[...s.assets.map(a=>a.position[0]),rx];const lo=Math.min(...xs),hi=Math.max(...xs);const span=Math.max(30,hi-lo);const cx=(lo+hi)/2;
  return {target:[cx,0,8] as [number,number,number],position:[cx+span*.35,span*.42,8+span*.8] as [number,number,number]};});
 return <><LiveStrip snap={snap}/><section className="mission-scene">
  <div className="scene-canvas"><Boundary><Canvas shadows camera={{position:view.position,fov:48}} dpr={[1,1.6]}><Scene s={s} at={at} labels={labels}/><OrbitControls makeDefault minDistance={12} maxDistance={260} maxPolarAngle={Math.PI/2.15} target={view.target}/></Canvas></Boundary></div>
  <div className="scene-hud">
   <div className="hud-block"><small>{replay?`REPLAY · revision ${replay.n}`:'LIVE · real Mars time'}</small><strong>{solOf(s.tick)} · step {s.tick}</strong>{c&&<span>Sun {c.site_solar_elevation_deg>0?`${fmt(c.site_solar_elevation_deg,0)}° up`:`${fmt(-c.site_solar_elevation_deg,0)}° below the horizon`} · {c.season}</span>}</div>
   <div className="hud-block"><small>NOW</small>{running.length?running.map(j=><span key={j.id}>▶ {j.title} · {fmt(j.progress*100,0)}%</span>):<span>No robot is working.</span>}
    {flying.map(j=><span key={j.id}>✉ {j.title}: in flight, arrives {at(j.uplink!.arrival_tick!)}{j.uplink?.via?.[0]?` (via ${j.uplink.via[0]})`:''}</span>)}
    {waiting.map(j=><span key={j.id}>⏳ {j.title}: {heldText(j)}</span>)}
    {!replay&&!running.length&&!flying.length&&!waiting.length&&<span>{s.planning_status}</span>}</div>
   <div className="hud-block replay"><small>REPLAY FROM GENESIS</small>
    <input type="range" min={revs[0]?.revision||1} max={revs.at(-1)?.revision||1} value={replay?.n||revs.at(-1)?.revision||1} onChange={e=>{setPlaying(false);load(Number(e.target.value));}} aria-label="Replay revision"/>
    <div><button onClick={()=>{if(!revs.length)return;if(!replay)load(revs[0].revision);setPlaying(p=>!p);}}>{playing?'Pause':'Play'}</button><button onClick={()=>{setPlaying(false);setReplay(null);}} disabled={!replay}>Stop · back to live</button></div></div>
  </div>
  <p className="scene-note">Robots move only while their work is running in the simulation; waiting robots stay still and say why. Sun position is computed for the site at this moment. The rover's position is the distance driven in the simulation along its survey line (east, per the route planner); trench size is the published habitat size and depth. Ground: HiRISE orbital image nearest the site (single band, coloured), not to scale. Lighting follows the real sun elevation at the site; the twilight shading curve is illustrative. Layout positions, the spoil pile, excavator shuttling and models are illustrative.</p>
 </section></>;
}
