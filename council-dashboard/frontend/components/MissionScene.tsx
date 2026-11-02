'use client';
// The mission, live: robots move when their work is running, wait visibly when it is not,
// and the sun sits where it really is over the site right now.
// Motion is a visualization of the simulated job state (progress, assignments); models are illustrative stand-ins.
import {Canvas,useFrame,useLoader} from '@react-three/fiber';
import {OrbitControls,Html,useGLTF,Line} from '@react-three/drei';
import {useMemo,useRef,useState,useEffect,Suspense,Component,ReactNode} from 'react';
import * as THREE from 'three';
import {State,Asset,Job,Snapshot,api,solOf,fmt} from '../lib/mission';
import LiveStrip,{useLive,LiveClock} from './LiveStrip';

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
// D10: agents run onboard; an authorized order waits only for onboard assurance, then runs.
const inReview=(j:Job)=>j.status==='review';
// D18: battery state of charge as a percentage, for battery-powered units only.
const pct=(a:Asset)=>{const b=a as unknown as {battery_wh?:number|null;soc_wh?:number};return b.battery_wh?Math.round(100*(b.soc_wh??0)/b.battery_wh):null;};
const charging=(a:Asset)=>Boolean((a as unknown as {charging?:boolean}).charging);
const standby=(s:State,a:Asset)=>((a as unknown as {standby_until_tick?:number}).standby_until_tick||0)>s.tick;
// D18: a battery unit cannot work a step its charge cannot supply (rate x step length x energy per kg, as the engine).
const lowBattery=(s:State,a:Asset)=>{const b=a as unknown as {battery_wh?:number|null;soc_wh?:number;energy_wh_per_kg?:number};return Boolean(b.battery_wh)&&(b.soc_wh??0)<(a.rate_per_h||0)*s.spec.tick_hours*(b.energy_wh_per_kg||0)-1e-9;};
// A job that is running but not progressing right now says why in its reason (engine): paused, standby or night.
export const pausedJob=(j:Job)=>j.status==='running'&&/^(Paused|Standby|Night)/.test(j.reason||'');
// HUD line for a running job: ▶ only when at least one of its units is working now; otherwise ⏸ and why.
function hudLine(s:State,j:Job,night:boolean){
 const units=j.assigned.map(id=>s.assets.find(a=>a.id===id)).filter((a):a is Asset=>Boolean(a));const pc=`${j.title} · ${fmt(j.progress*100,0)}%`;
 if(units.some(a=>working(s,a,night)))return `▶ ${pc}`;
 const why=night&&units.some(a=>a.kind==='rover')?'waiting for daylight (D19)':units.some(a=>standby(s,a))?'standby':units.every(a=>charging(a))?'charging':units.some(a=>lowBattery(s,a))?'batteries too low; recharge needed':units.some(a=>!a.available)?'equipment unavailable':(j.reason||'not progressing');
 return `⏸ ${pc} · ${why}`;
}
// Whether this unit is actually working at this moment, by the same rules the engine applies to the step.
const working=(s:State,a:Asset,night=false)=>{const j=jobOf(s,a);return Boolean(a.available&&j&&j.status==='running'&&!standby(s,a)&&!charging(a)&&!lowBattery(s,a)&&!(night&&a.kind==='rover'));};

export function Ground(){
 const tex=useLoader(THREE.TextureLoader,'/api/v1/site/ground.jpg');
 useMemo(()=>{tex.wrapS=tex.wrapT=THREE.RepeatWrapping;tex.repeat.set(16,16);tex.colorSpace=THREE.SRGBColorSpace;tex.anisotropy=8;},[tex]);
 // HiRISE RED is a single band; multiplying by a regolith colour gives the familiar ochre without inventing detail.
 return <mesh rotation={[-Math.PI/2,0,0]} receiveShadow><planeGeometry args={[1600,1600]}/><meshStandardMaterial map={tex} color="#d08a5c" roughness={1}/></mesh>;
}
export class GroundBoundary extends Component<{children:ReactNode},{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return {failed:true};}render(){return this.state.failed?<PlainGround/>:this.props.children;}}
export function PlainGround(){return <mesh rotation={[-Math.PI/2,0,0]} receiveShadow><planeGeometry args={[1600,1600]}/><meshStandardMaterial color="#b9734a" roughness={1}/></mesh>;}

// Survey: the rover drives the simulated survey distance, east from its start (the route planner's west-to-east
// convention, D13). Its position is the metres driven in the simulation (job.done). On the live public mission it also
// advances through the step in progress at the authorized rate (the decision's rate per step) in proportion to the time
// elapsed toward the next step, never beyond the remaining distance; the step's result is recorded when the step runs.
const surveyJobs=(s:State)=>s.jobs.filter(j=>j.kind==='survey');
// D19: no driving while the live sun is below the horizon; in daylight the rate is the one the last step used.
export type StepClock={next:number;len:number;sunUp:boolean};
function inStep(s:State,a:Asset,clock:StepClock|null){
 const j=jobOf(s,a);if(!clock||!clock.sunUp||!a.available||j?.status!=='running'||j.kind!=='survey'||standby(s,a))return 0;
 const rate=(j as unknown as {day_rate_per_tick?:number|null}).day_rate_per_tick??s.decisions.find(d=>d.id===j.decision_id)?.calculation.rate_per_tick;if(!rate)return 0;
 const f=Math.max(0,Math.min(1,1-(clock.next-Date.now()/1000)/clock.len));
 return Math.min(rate*f,j.target-j.done);
}
function Rover({a,s,clock,labels,night}:{a:Asset;s:State;clock:StepClock|null;labels:boolean;night:boolean}){
 const ref=useRef<THREE.Group>(null);const j=jobOf(s,a);const moving=j?.kind==='survey'&&working(s,a,night);// D19: no driving at night
 const driven=surveyJobs(s).reduce((t,x)=>t+x.done,0);const at=useMemo(()=>new THREE.Vector3(),[]);
 useFrame((_,dt)=>{if(!ref.current)return;at.set(a.position[0]+driven+inStep(s,a,clock),0,a.position[2]);ref.current.position.lerp(at,1-Math.exp(-dt*2));});
 return <group ref={ref} position={a.position}><group rotation={[0,Math.PI/2,0]}><Suspense fallback={null}><Model file={FILE.rover[0]} size={FILE.rover[1]} tint={a.available?null:'#7a2c12'}/></Suspense>{moving&&<Dust/>}</group>
  {labels&&<Html position={[0,FILE.rover[1]+1.4,0]} center><Tag s={s} a={a} night={night}/></Html>}</group>;
}
function SurveyLine({a,s}:{a:Asset;s:State}){
 const jobs=surveyJobs(s);if(!jobs.length)return null;
 const planned=jobs.reduce((t,x)=>t+x.target,0),driven=jobs.reduce((t,x)=>t+x.done,0);const main=jobs.find(x=>x.id==='survey');
 const y=.08,x0=a.position[0],z=a.position[2];
 const survey=main as unknown as {route?:{detour_factor:number;base_target:number};route_blocked?:{status:string}}|undefined;const route=survey?.route;
 const label=`Survey drive ${fmt(driven,1)} / ${fmt(planned,2)} m`+(survey?.route_blocked?` · blocked: ${survey.route_blocked.status} (SAM, D13)`:route?` · hazard detour ×${route.detour_factor} applied (SAM, D13)`:' · no hazard detour applied');
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
 const ref=useRef<THREE.Group>(null);const j=jobOf(s,a);const moving=working(s,a);
 const hab=s.assets.find(x=>x.kind==='habitat');const TRENCH=trenchAt(s);
 const target=j?.id==='shielding'&&hab?new THREE.Vector3(...hab.position):SPOIL;const home=new THREE.Vector3(...a.position);
 useFrame(({clock})=>{if(!ref.current)return;if(moving){const f=(Math.sin(clock.elapsedTime*0.6+i*1.7)+1)/2;const p=TRENCH.clone().add(new THREE.Vector3(i*2-1,0,0)).lerp(target,f);ref.current.position.lerp(p,0.1);ref.current.rotation.y=Math.atan2(target.x-TRENCH.x,target.z-TRENCH.z)+(Math.cos(clock.elapsedTime*0.6+i*1.7)>0?0:Math.PI);}else ref.current.position.lerp(home,0.05);});
 return <group ref={ref} position={a.position}><Suspense fallback={null}><Model file={FILE.excavator[0]} size={FILE.excavator[1]} tint={a.available?null:'#7a2c12'}/></Suspense></group>;
}
function Drill({a,s}:{a:Asset;s:State}){
 const ref=useRef<THREE.Group>(null);const d=s.jobs.find(j=>j.id==='drill');const w=s.jobs.find(j=>j.id==='water');
 const spinning=working(s,a)&&(d?.status==='running'||w?.status==='running');
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
function Tag({s,a,night=false}:{s:State;a:Asset;night?:boolean}){
 const j=jobOf(s,a);const sb=standby(s,a);const dark=night&&a.kind==='rover'&&j?.status==='running'&&j.kind==='survey';
 const p=pct(a);const bat=p===null?'':` · battery ${p}%`;
 const txt=!a.available?'FAILED':charging(a)?`Charging from the grid · battery ${p}%`:sb?`Standby: ${(a as unknown as {standby?:{reason:string}}).standby?.reason??'reason not recorded'}`:dark?`${j.title} · ${fmt(j.progress*100,0)}% · waiting for daylight (D19)`:j?.status==='running'&&lowBattery(s,a)?`Battery too low for a step · ${p}% · recharge needed`:j?.status==='running'?`${j.title} · ${fmt(j.progress*100,0)}%${bat}`:j&&inReview(j)?`Authorized · awaiting onboard assurance${bat}`:`Idle${bat}`;
 const cls=!a.available?'failed':charging(a)?'waiting':sb?'standby':dark?'waiting':j?.status==='running'&&lowBattery(s,a)?'waiting':j?.status==='running'?'working':j&&inReview(j)?'held':'idle';
 return <span className={'scene-tag '+cls}><b>{a.name.split(' (')[0]}</b>{txt}</span>;
}
// The rover carries its own tag so it follows the rover; the other units stay put.
function Tags({s}:{s:State}){
 return <>{s.assets.filter(a=>a.kind!=='rover').map(a=><Html key={a.id} position={[a.position[0],(FILE[a.kind]?.[1]||2)+1.4,a.position[2]]} center><Tag s={s} a={a}/></Html>)}</>;
}
function Scene({s,labels,clock,sun}:{s:State;labels:boolean;clock:StepClock|null;sun:[number,number,number]|null}){
 const night=sun!==null&&sun[2]<=0;// sun below the horizon at the site
 // sun: the live Mars24 sun direction at the site (live view, read every 30 s) or the one recorded with the step (replay).
 // None -> neutral light, no invented sun.
 const sunPos:[number,number,number]|null=sun?[sun[0]*80,sun[2]*80,-sun[1]*80]:null;
 // Brightness follows the real solar elevation continuously (twilight before sunrise and after sunset), instead of a
 // day/night switch. The shading curve is a display mapping, not a measured sky brightness.
 const elev=sun?Math.asin(Math.max(-1,Math.min(1,sun[2])))*180/Math.PI:null;
 const ease=(a:number,b:number,x:number)=>{const t=Math.max(0,Math.min(1,(x-a)/(b-a)));return t*t*(3-2*t);};
 const k=elev==null?1:ease(-12,6,elev),direct=elev==null?0:ease(-1,6,elev);
 const mix=(n:string,d:string)=>'#'+new THREE.Color(n).lerp(new THREE.Color(d),k).getHexString();
 return <>
  <color attach="background" args={[mix('#140d0b','#d7a77f')]}/>{/* Mars daytime sky: butterscotch from suspended dust */}
  <ambientLight intensity={0.08+0.37*k}/><hemisphereLight args={['#f1c9a4','#3a2418',0.08+0.52*k]}/>
  {sunPos?<directionalLight position={sunPos} intensity={0.05+2.55*direct} castShadow shadow-mapSize={[2048,2048]} shadow-camera-left={-40} shadow-camera-right={40} shadow-camera-top={40} shadow-camera-bottom={-40}/>:<ambientLight intensity={0.5}/>}
  <fog attach="fog" args={[mix('#120c0a','#d6a98a'),120,420]}/>
  <GroundBoundary><Suspense fallback={<PlainGround/>}><Ground/></Suspense></GroundBoundary>
  <Site s={s}/>
  {s.assets.filter(a=>a.kind==='rover').map(a=><SurveyLine key={'line-'+a.id} a={a} s={s}/>)}
  {s.assets.map((a,i)=>a.kind==='rover'?<Rover key={a.id} a={a} s={s} clock={clock} labels={labels} night={night}/>:a.kind==='excavator'?<Excavator key={a.id} a={a} s={s} i={i}/>:a.kind==='rodwell'?<Drill key={a.id} a={a} s={s}/>:a.kind==='power'?<Power key={a.id} a={a} s={s}/>:null)}
  {labels&&<Tags s={s}/>}
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
 // Clock time of a future step, from the server's next-step time and step length only; unknown if either is missing.
 const running=s.jobs.filter(j=>j.status==='running');const reviewing=s.jobs.filter(inReview);const charging_=s.assets.filter(charging);
 // Light follows the sun continuously: the live view uses the server's live Mars24 reading (polled every 30 s);
 // a replay uses the sun recorded with each step.
 const feed=useLive();
 const c:LiveClock|undefined=!replay&&feed.live?.now?.clock?feed.live.now.clock:s.environment?.clock;
 // Live public mission only: the time to the next step, from the server's schedule. None in replays or experiments.
 const clock:StepClock|null=!replay&&s.status==='active'&&snap.next_tick_at!=null&&snap.seconds_per_tick&&c?{next:snap.next_tick_at,len:snap.seconds_per_tick,sunUp:c.site_solar_elevation_deg>0}:null;
 // Opening view frames the outpost and the rover's current point on its survey line (camera only; set once per visit).
 const [view]=useState(()=>{const rover=s.assets.find(a=>a.kind==='rover');const rx=rover?rover.position[0]+surveyJobs(s).reduce((t,x)=>t+x.done,0):0;
  const xs=[...s.assets.map(a=>a.position[0]),rx];const lo=Math.min(...xs),hi=Math.max(...xs);const span=Math.max(30,hi-lo);const cx=(lo+hi)/2;
  return {target:[cx,0,8] as [number,number,number],position:[cx+span*.35,span*.42,8+span*.8] as [number,number,number]};});
 return <><LiveStrip snap={snap} feed={feed}/><section className="mission-scene">
  <div className="scene-canvas"><Boundary><Canvas shadows camera={{position:view.position,fov:48}} dpr={[1,1.6]}><Scene s={s} labels={labels} clock={clock} sun={c?.site_sun_enu??null}/><OrbitControls makeDefault minDistance={12} maxDistance={260} maxPolarAngle={Math.PI/2.15} target={view.target}/></Canvas></Boundary></div>
  <div className="scene-hud">
   <div className="hud-block"><small>{replay?`REPLAY · revision ${replay.n}`:'LIVE · real Mars time'}</small><strong>{solOf(s.tick)} · step {s.tick}</strong>{c&&<span>Sun {c.site_solar_elevation_deg>0?`${fmt(c.site_solar_elevation_deg,0)}° up`:`${fmt(-c.site_solar_elevation_deg,0)}° below the horizon`} · {c.season}</span>}</div>
   <div className="hud-block"><small>NOW</small>{running.length?running.map(j=><span key={j.id}>{hudLine(s,j,Boolean(c&&c.site_solar_elevation_deg<=0))}</span>):<span>No robot is working.</span>}
    {reviewing.map(j=><span key={j.id}>⏳ {j.title}: authorized, awaiting onboard assurance</span>)}
    {charging_.map(a=><span key={a.id}>⚡ {a.name.split(' (')[0]} charging · battery {pct(a)}%</span>)}
    {!replay&&!running.length&&!reviewing.length&&!charging_.length&&<span>{s.planning_status}</span>}</div>
   <div className="hud-block replay"><small>REPLAY FROM GENESIS</small>
    <input type="range" min={revs[0]?.revision||1} max={revs.at(-1)?.revision||1} value={replay?.n||revs.at(-1)?.revision||1} onChange={e=>{setPlaying(false);load(Number(e.target.value));}} aria-label="Replay revision"/>
    <div><button onClick={()=>{if(!revs.length)return;if(!replay)load(revs[0].revision);setPlaying(p=>!p);}}>{playing?'Pause':'Play'}</button><button onClick={()=>{setPlaying(false);setReplay(null);}} disabled={!replay}>Stop · back to live</button></div></div>
  </div>
  <p className="scene-note">Robots move only while their work is running in the simulation; waiting robots stay still and say why. Sun position is computed for the site at this moment. The rover's position is the distance driven in the simulation along its survey line (east, per the route planner); between steps it advances at its authorized rate toward the next recorded step, and it drives only in daylight (D19); trench size is the published habitat size and depth. Ground: HiRISE orbital image nearest the site (single band, coloured), not to scale. Lighting follows the real sun elevation at the site; the twilight shading curve is illustrative. Layout positions, the spoil pile, excavator shuttling and models are illustrative.</p>
 </section></>;
}
