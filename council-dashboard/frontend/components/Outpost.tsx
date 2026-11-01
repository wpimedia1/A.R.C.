'use client';
import {Canvas,useFrame} from '@react-three/fiber';
import {OrbitControls,ContactShadows,Html,useGLTF} from '@react-three/drei';
import {useMemo,useState,Component,ReactNode,Suspense} from 'react';
import * as THREE from 'three';
import {State,Asset} from '../lib/mission';
class Boundary extends Component<{children:ReactNode},{failed:boolean}>{state={failed:false};static getDerivedStateFromError(){return {failed:true};}render(){return this.state.failed?<p className="fallback">3D is unavailable. Use the equipment list below.</p>:this.props.children;}}
function Model({name,size=3,muted=false}:{name:string;size?:number;muted?:boolean}){
 // Draco decoder is self-hosted (copied from three/examples/jsm/libs/draco/gltf) so no CDN is needed.
 const {scene}=useGLTF(name==='perseverance'?'/models/perseverance.glb':`/models/kenney/${name}.glb`,'/draco/');
 const model=useMemo(()=>{const clone=scene.clone(true),box=new THREE.Box3().setFromObject(clone),d=box.getSize(new THREE.Vector3()),c=box.getCenter(new THREE.Vector3()),k=size/Math.max(d.x,d.y,d.z);clone.scale.setScalar(k);clone.position.set(-c.x*k,-box.min.y*k,-c.z*k);clone.traverse(o=>{if(o instanceof THREE.Mesh){o.castShadow=true;o.receiveShadow=true;if(muted){const l=Array.isArray(o.material)?o.material:[o.material];o.material=l.map(m=>{const x=m.clone();x.transparent=true;x.opacity=.3;x.depthWrite=false;return x;});}}});return clone;},[scene,size,muted]);
 return <primitive object={model}/>;
}
// Illustrative stand-in models (Kenney CC0, NASA Perseverance). Not engineering representations.
const MODEL:Record<string,[string,number]>={rover:['perseverance',2.3],excavator:['rover',1.4],rodwell:['machine_barrelLarge',1.8],power:['machine_generatorLarge',3],habitat:['hangar_roundB',5]};
function Equipment({a,state,select,labels}:{a:Asset;state:State;select:(id:string)=>void;labels:boolean}){
 const job=state.jobs.find(j=>j.assigned.includes(a.id))||state.jobs.find(j=>j.asset_kinds.includes(a.kind));
 const [name,size]=MODEL[a.kind];
 const trench=state.jobs.find(j=>j.id==='trench');
 const muted=a.kind==='habitat'&&trench?.status!=='complete';
 return <><group position={a.position} onClick={e=>{e.stopPropagation();if(job)select(job.id);}}><Suspense fallback={null}><Model name={name} size={size} muted={muted||!a.available}/></Suspense></group>
  {labels&&<Html position={[a.position[0],size+.8,a.position[2]]} center><button className="asset-tag" onClick={()=>job&&select(job.id)}>{a.name}<small>{!a.available?'Unavailable':job&&job.assigned.includes(a.id)?`${job.title} · ${(job.progress*100).toFixed(0)}%`:a.kind==='power'?`${state.power_used_kw.toFixed(2)} / ${state.power_capacity_kw} kW allocated`:'Idle'}</small></button></Html>}</>;
}
// Labels mount after the first rendered frame; mounting drei Html during the first commit dropped one label.
function Scene({state,select}:{state:State;select:(id:string)=>void}){
 const [labels,setLabels]=useState(false);
 useFrame(()=>{if(!labels)setLabels(true);});
 return <>{state.assets.map(a=><Equipment key={a.id} a={a} state={state} select={select} labels={labels}/>)}</>;
}
export default function Outpost({state,select}:{state:State;select:(id:string)=>void}){
 return <Boundary><Canvas shadows camera={{position:[17,16,22],fov:43}} dpr={[1,1.5]} aria-label="Equipment layout diagram; positions are display-only"><color attach="background" args={['#ba8870']}/><fog attach="fog" args={['#ba8870',40,90]}/><ambientLight intensity={.85}/><hemisphereLight args={['#efd7bf','#483c36',1.1]}/><directionalLight position={[-12,20,8]} intensity={3} castShadow shadow-mapSize={[2048,2048]}/>
  <gridHelper args={[90,30,'#8b8274','#bcb3a4']}/><mesh rotation={[-Math.PI/2,0,0]} position={[0,-.02,0]} receiveShadow><planeGeometry args={[90,70]}/><meshStandardMaterial color="#d2c9ba" roughness={1}/></mesh>
  <Scene state={state} select={select}/>
  <ContactShadows opacity={.28} scale={60} blur={2} far={10} resolution={512}/><OrbitControls makeDefault minDistance={12} maxDistance={55} maxPolarAngle={Math.PI/2.2}/></Canvas></Boundary>;
}
