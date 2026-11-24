/** @jsx jsx */
import {h as jsx, Fragment, render} from "preact";

// ClipKaro-owned biped rig and deterministic director executor. No model code is evaluated.
type Item = Record<string, any>;
const clamp=(v:number,a=0,b=1)=>Math.max(a,Math.min(b,v));
const mix=(a:number,b:number,t:number)=>a+(b-a)*t;
const ease=(v:number)=>{v=clamp(v);return v*v*(3-2*v)};
const progress=(t:number,a:number,b:number)=>ease((t-a)/Math.max(.001,b-a));
const rad=(a:number)=>a*Math.PI/180;
const chars=(story:Item)=>new Map<string,Item>(story.characters.map((c:Item)=>[c.id,c]));

export function actorState(scene:Item,actor:Item,t:number,index=0):Item {
  const state:Item={...actor,pose:actor.pose||"stand",poseMix:actor.pose==="sleep"?1:actor.pose==="sit"?.28:0,expression:"neutral",gaze:0,head:0,wave:0,reach:0,gait:0,step:0,blink:0,held:null};
  for(const a of scene.actions.filter((a:Item)=>a.character_id===actor.character_id && a.start<=t)) {
    const p=progress(t,a.start,a.end),active=t<a.end;
    if(["walk","run"].includes(a.type)&&a.to) {
      state.x=mix(state.x,a.to.x,p);state.y=mix(state.y,a.to.y,p);
      state.pose="stand";state.gait=active?(a.type==="run"?1.6:1):0;
      state.poseMix=0;
      state.step=(t-a.start)*(a.type==="run"?12:7);
      state.facing=a.to.x<actor.x?-1:1;
    }
    if(["sleep","sit","stand"].includes(a.type)) {state.poseMix=mix(state.poseMix,a.type==="sleep"?1:a.type==="sit"?.28:0,p);state.pose=a.type;}
    if(a.type==="wake") {state.poseMix=mix(state.poseMix,.28,p);state.pose=p>.2?"sit":"sleep";state.wake=p;}
    if(a.type==="react")state.expression=a.expression;
    if(a.type==="turn"||a.type==="look")state.gaze=a.value*p;
    if(a.type==="head")state.head=a.value*10*p;
    if(a.type==="blink"&&active)state.blink=Math.sin(Math.PI*p);
    if(a.type==="wave"&&active)state.wave=Math.sin((t-a.start)*9)*28;
    if(a.type==="wag"&&active)state.tailWag=Math.sin((t-a.start)*12)*13*a.value;
    if(a.type==="jump"&&active)state.jump=Math.sin(Math.PI*p)*70;
    if(["point","reach","pick_up","put_down","open_door","close_door","open_box","open_book"].includes(a.type)) {
      if(active) {state.reach=Math.sin(Math.PI*p);state.target=a.target_id;state.reachAction=a.type;}
      if(a.type==="pick_up"&&p>.5)state.held=a.target_id;
      if(a.type==="put_down"&&p>.5)state.held=null;
    }
  }
  const blink=clamp(1-Math.abs(((t+index*.57)%4.6)-3.9)/.12);
  state.blink=Math.max(state.blink,blink);
  return state;
}

function poseAmount(state:Item,t:number) {
  return state.poseMix;
}

export function armPoints(state:Item,side:number) {
  const shoulder={x:side*56,y:-246};
  const walk=Math.sin(state.step+ (side===1?Math.PI:0))*state.gait*21;
  const angle=side===1?state.wave+state.reach*-78+walk:-walk;
  const rotate=(x:number,y:number)=>({x:shoulder.x+(x-shoulder.x)*Math.cos(rad(angle))-(y-shoulder.y)*Math.sin(rad(angle)),y:shoulder.y+(x-shoulder.x)*Math.sin(rad(angle))+(y-shoulder.y)*Math.cos(rad(angle))});
  let elbow=rotate(side*78,-187),hand=rotate(side*75,-128);
  if(side===1&&state.localTarget&&state.reach>0) {
    hand={x:mix(75,state.localTarget.x,state.reach),y:mix(-128,state.localTarget.y,state.reach)};
    const dx=hand.x-shoulder.x,dy=hand.y-shoulder.y,distance=Math.hypot(dx,dy),d=Math.min(143.5,distance);
    hand={x:shoulder.x+dx*d/Math.max(1,distance),y:shoulder.y+dy*d/Math.max(1,distance)};
    const mid={x:(shoulder.x+hand.x)/2,y:(shoulder.y+hand.y)/2},height=Math.sqrt(Math.max(0,72*72-d*d/4));
    elbow={x:mid.x+dy/Math.max(1,distance)*height,y:mid.y-dx/Math.max(1,distance)*height};
  }
  return {shoulder,elbow,hand};
}

function Arm({side,state,skin,cloth,ink,t}:Item) {
  const {shoulder,elbow,hand}=armPoints(state,side);
  return <g>
    <path d={`M${shoulder.x} ${shoulder.y} Q${elbow.x} ${elbow.y-8} ${elbow.x} ${elbow.y}`} fill="none" stroke={ink} stroke-width="38" stroke-linecap="round"/>
    <path d={`M${shoulder.x} ${shoulder.y} Q${elbow.x} ${elbow.y-8} ${elbow.x} ${elbow.y}`} fill="none" stroke={cloth} stroke-width="32" stroke-linecap="round"/>
    <path d={`M${elbow.x} ${elbow.y}L${hand.x} ${hand.y}`} fill="none" stroke={skin} stroke-width="23" stroke-linecap="round"/>
    <path d={`M${hand.x-10} ${hand.y-7}q-10 12 0 27q7 6 11-2q12 4 12-8l-6-17Z`} fill={skin} stroke={ink} stroke-width="1.6"/>
  </g>;
}

export function Biped({character,state,t,x,y,scale,prefix,mouth=0,viseme="open"}:Item) {
  const app=character.appearance, ink="#182B3B", skin=app.skin_color;
  const sleep=poseAmount(state,t),rot=sleep>.3?(sleep-.28)/.72*-82:0;
  const sit=clamp(sleep/.28)*(1-clamp((sleep-.28)/.72));
  const bob=Math.sin(t*2.8)*1.7;
  const leg=Math.sin(state.step)*state.gait*24;
  const eye=Math.max(.04,1-state.blink);
  const asleep=state.pose==="sleep"&&(state.wake==null||state.wake<.2);
  const sad=["sad","scared"].includes(state.expression),scared=["scared","surprised"].includes(state.expression);
  const faceWidth=app.face_shape==="round"?78:app.face_shape==="angular"?67:71;
  const headAngle=state.head+state.gaze*3;
  const hair=app.hair_color, shirt=app.shirt_color, pants=app.pants_color, shoe=app.shoe_color;
  const long=app.hair_style==="long",longClothes=["kameez","dress"].includes(app.clothing);
  const animal=!["human","robot"].includes(character.species);
  const dog=character.species==="dog",robot=character.species==="robot";
  const skinId=prefix+"-skin",clothId=prefix+"-cloth";
  const dy=65*clamp(sleep/.28)*(1-clamp((sleep-.28)/.72))+(state.bodyOffset||0);
  return <g data-character-id={character.id} transform={`translate(${x} ${y-(state.jump||0)*scale}) scale(${scale})`}>
    <defs><linearGradient id={skinId}><stop stop-color={skin}/><stop offset="1" stop-color={skin} stop-opacity=".76"/></linearGradient>
    <linearGradient id={clothId} x2="1" y2=".3"><stop stop-color={shirt}/><stop offset="1" stop-color={pants}/></linearGradient></defs>
    <ellipse cx="0" cy="5" rx={85+state.gait*8} ry="10" fill="#071421" opacity=".25"/>
    <g transform={`translate(0 ${dy+bob}) rotate(${rot} 0 -112)`}>
      {animal&&["fox","cat","dog"].includes(character.species)&&<g transform={`rotate(${state.tailWag||0} 52 -129)`}>
        <path d={dog?"M52-129Q125-130 143-183":"M52-129Q144-197 140-98Q138-45 68-47"} stroke={skin} stroke-width={dog?23:31} fill="none" stroke-linecap="round"/>
        {character.species==="fox"&&<path d="M131-87Q118-49 73-48" stroke="#EDE5D0" stroke-width="23" fill="none" stroke-linecap="round"/>}
      </g>}
      <g transform={`rotate(${leg} -24 -110)`}>
        <path d={`M-24-112L${-27-sit*25-(state.crouch||0)*27} ${-60+sit*18}L${-30-sit*48} ${-10-dy}`} fill="none" stroke={ink} stroke-width="35" stroke-linecap="round"/>
        <path d={`M-24-112L${-27-sit*25-(state.crouch||0)*27} ${-60+sit*18}L${-30-sit*48} ${-10-dy}`} fill="none" stroke={pants} stroke-width="30" stroke-linecap="round"/>
        <path transform={`translate(0 ${-dy})`} d={`M${-45-sit*48}-16q-24 4-23 15h50v-15Z`} fill={shoe}/></g>
      <g transform={`rotate(${-leg} 24 -110)`}>
        <path d={`M24-112L${27+sit*25+(state.crouch||0)*27} ${-60+sit*18}L${30+sit*48} ${-10-dy}`} fill="none" stroke={ink} stroke-width="35" stroke-linecap="round"/>
        <path d={`M24-112L${27+sit*25+(state.crouch||0)*27} ${-60+sit*18}L${30+sit*48} ${-10-dy}`} fill="none" stroke={pants} stroke-width="30" stroke-linecap="round"/>
        <path transform={`translate(0 ${-dy})`} d={`M${16+sit*48}-16v15h50q1-11-23-15Z`} fill={shoe}/></g>
      <g transform={`rotate(${state.bend||0} 0 -112)`}>
      {long&&<path d="M-71-362Q-95-285-79-232L73-229Q89-305 74-364Z" fill={hair} stroke={ink} stroke-width="3"/>}
      <Arm side={-1} {...{state,t,skin,cloth:shirt,ink}}/>
      <path d={`M-56-257Q-36-269-22-264Q0-249 24-264Q44-268 58-252L${longClothes?78:55} ${longClothes?-69:-113}Q0 ${longClothes?-51:-98}-${longClothes?78:55} ${longClothes?-69:-113}Z`} fill={`url(#${clothId})`} stroke={ink} stroke-width="3"/>
      <path d="M-23-262Q0-247 23-262M-36-227Q-40-175-30-132M35-222Q28-168 38-126" fill="none" stroke="#D4E9DE" opacity=".28" stroke-width="2.5"/>
      {Array.from({length:3},(_,i)=><circle key={i} cx="0" cy={-238+i*13} r="2.4" fill="#CADAD2"/>)}
      <g transform={`translate(${state.gaze*5} 0) rotate(${headAngle} 0 -266) translate(0 -340) scale(${1-Math.abs(state.gaze)*.10} 1) translate(0 340)`}>
        <path d="M-24-295V-259Q0-244 24-259V-295Z" fill={skin} stroke={ink} stroke-width="2"/>
        {long&&<path d="M-73-356Q-90-435-18-443Q60-455 78-382L86-263Q60-247 58-282L-58-285Q-64-253-83-268Z" fill={hair}/>}
        <ellipse cx="-70" cy="-347" rx="13" ry="22" fill={skin} stroke={ink} stroke-width="2"/>
        <ellipse cx="70" cy="-347" rx="13" ry="22" fill={skin} stroke={ink} stroke-width="2"/>
        <path d={`M-${faceWidth}-390Q-55-435 0-433Q55-435 ${faceWidth}-390L${faceWidth-1}-345Q63-291 12-277Q0-273-12-277Q-63-291-${faceWidth-1}-345Z`} fill={`url(#${skinId})`} stroke={ink} stroke-width="2.5"/>
        <path d="M36-424Q83-372 57-322Q43-291 9-278Q65-285 72-350L72-390Z" fill="#182B3B" opacity=".13"/>
        {!animal&&app.hair_style!=="bald"&&<path d={app.hair_style==="curly"?"M-73-363Q-96-402-66-419Q-56-456-18-435Q16-465 41-432Q89-443 78-374L46-406L0-417L-40-396Z":app.hair_style==="spiky"?"M-75-367L-71-424L-40-410L-18-454L5-420L39-454L49-410L78-427L77-363L40-403L0-418L-43-399Z":"M-74-363Q-94-429-20-445Q55-461 78-393L78-368Q52-404 5-425Q-20-405-49-402Q-66-390-74-363Z"} fill={hair} stroke={ink} stroke-width="2"/>}
        {animal&&<ellipse cy="-319" rx="48" ry="31" fill="#EBDBC2"/>}
        {long&&<><path d="M-65-401Q-78-354-64-308L-73-276" fill="none" stroke={hair} stroke-width="9"/><path d="M65-405Q83-356 69-309L78-270" fill="none" stroke={hair} stroke-width="9"/></>}
        {[-1,1].map(side=><g key={side}>
          <path d={`M${side*39-20} ${-380+(sad?5:0)}Q${side*39} ${-390-(sad?5:0)} ${side*39+20} ${-380+(sad?3:0)}`} fill="none" stroke={hair} stroke-width="6" stroke-linecap="round"/>
          {asleep?<path d={`M${side*36-21}-351Q${side*36}-339 ${side*36+21}-351`} stroke={ink} stroke-width="4" fill="none"/>:
          <g transform={`translate(${side*35+state.gaze*5} -352) scale(1 ${eye})`}>
            <path d={`M-23 0Q-8 ${scared?-23:-18} 10-15Q20-10 23 0Q7 14-10 9Q-18 6-23 0Z`} fill="#E9E7DC" stroke={ink} stroke-width="3"/>
            <ellipse cx={state.gaze*7} cy="-1" rx="10" ry="13" fill={app.eye_color}/><ellipse cx={state.gaze*7} cy="-1" rx="5" ry="9" fill="#0C1B2B"/><circle cx={state.gaze*7-3} cy="-6" r="3" fill="#F4F3E6"/>
          </g>}
        </g>)}
        <path d={`M${6+state.gaze*4}-352q-7 19-7 28q6 7 14 0`} fill="none" stroke="#875D56" stroke-opacity=".6" stroke-width="2"/>
        {mouth>.1?<g><ellipse cx={5+state.gaze*3} cy="-305" rx={viseme==="round"?9:15} ry={3+mouth*10} fill="#5C3444" stroke="#875365" stroke-width="2"/><path d="M-4-310Q5-314 15-310" fill="none" stroke="#E5D6C8" stroke-width="2"/></g>:
        <path d={sad?"M-14-302Q6-310 23-302":state.expression==="angry"?"M-13-304H22":state.expression==="happy"?"M-16-307Q5-295 24-307":"M-14-304Q5-302 22-304"} fill="none" stroke="#905B63" stroke-width="3" stroke-linecap="round"/>}
        {animal&&<>{dog
          ?<path d="M-51-419Q-93-418-94-378Q-97-347-79-345Q-62-351-61-390Z M51-419Q93-418 94-378Q97-347 79-345Q62-351 61-390Z" fill={hair} stroke={ink} stroke-width="3"/>
          :<path d="M-61-394L-68-459L-21-418M61-394L68-459L21-418" fill={skin} stroke={ink} stroke-width="3"/>}
          <ellipse cy="-326" rx={dog?17:13} ry="8" fill="#263440"/></>}
        {robot&&<g stroke={ink} stroke-width="3">
          <path d="M0-435V-455" fill="none"/><circle cy="-461" r="7" fill="#B9E5E8"/>
          <circle cx="-60" cy="-331" r="3.5" fill="#B9E5E8"/><circle cx="60" cy="-331" r="3.5" fill="#B9E5E8"/>
        </g>}
        {state.expression==="sad"&&<ellipse cx="54" cy={-326+((t*.3)%1)*16} rx="2.5" ry="5" fill="#A4D4DE" opacity=".8"/>}
      </g>
      <Arm side={1} {...{state,t,skin,cloth:shirt,ink}}/>
      </g>
    </g>
  </g>;
}

export function propState(scene:Item,prop:Item,t:number) {
  let open=prop.state==="open"?1:0,held:string|null=prop.holder_id||null;
  for(const a of scene.actions) if(a.target_id===prop.id&&a.start<=t) {
    const p=progress(t,a.start,a.end);
    if(a.type==="open_door"||a.type==="open_box"||a.type==="open_book")open=p;
    if(a.type==="close_door")open=1-p;
    if(a.type==="pick_up"&&p>.5)held=a.character_id;
    if(a.type==="put_down"&&p>.5)held=null;
  }
  return {open,held};
}

function Prop({prop,x,y,unit,open=0}:Item) {
  const ink="#263444",c=prop.color||"#947666";
  const k=prop.type;
  return <g data-prop-id={prop.id} transform={`translate(${x} ${y}) scale(${unit})`}>
    {k==="door"?<><path d="M-90 0V-376H90V0Z" fill="#101C2A" stroke="#71808A" stroke-width="7"/><g transform={`translate(-84 0) scale(${1-open*.87} 1)`}><path d="M0-369H168V0H0Z" fill={c} stroke={ink} stroke-width="4"/><path d="M18-344H149V-202H18ZM18-181H149V-25H18Z" fill="#233242" fill-opacity=".35" stroke="#9D9290" stroke-width="2"/><path d="M137-173h-28" stroke="#D2BE91" stroke-width="7" stroke-linecap="round"/></g><path d="M-83 2H83" stroke="#D6BC87" stroke-width="3"/></>:
    k==="bed"?<><path d="M-250-5V-180h26V-26H265V5H-250" fill="#4D424A" stroke={ink} stroke-width="4"/><path d="M-227-119Q-221-144-180-143L240-135Q271-131 270-104V-48H-227Z" fill="#B3C8CC" stroke="#526777" stroke-width="4"/><path d="M-204-130q23-28 88-4l26 25q-20 20-115-4Z" fill="#D0DCDA"/><path d="M-227-72Q-12-94 270-67V-19H-227Z" fill="#776E91"/><path d="M-214 1V37M245 1V37" stroke="#353443" stroke-width="16"/></>:
    k==="table"?<><path d="M-100-122H100V-100H-100Z" fill={c} stroke={ink} stroke-width="3"/><path d="M-77-100L-86 0M77-100L86 0" stroke={c} stroke-width="13"/></>:
    k==="chair"?<><path d="M-51-175V-67H50V-175M-50-67V0M50-67V0" stroke={c} stroke-width="13" fill="none"/><path d="M-51-165H50V-99H-51Z" fill={c}/></>:
    k==="letter"?<><path d="M-30-42H30V0H-30Z" fill="#E9DCC5" stroke={ink} stroke-width="2"/><path d="M-30-42L0-18L30-42" fill="none" stroke="#A89483" stroke-width="2"/></>:
    k==="book"?<g data-book-open={open}>
      <path d="M-28-60H27V0H-28Z" fill={c} stroke={ink} stroke-width="3"/>
      {open>0&&<><path d="M-24-55H23V-5H-24Z" fill="#F4E5C6"/><path d="M-15-45H15M-15-35H15M-15-25H10" stroke="#988A70" stroke-width="2"/></>}
      <g transform={`translate(-28 0) scale(${1-2*open} 1)`}>
        <path d="M0-60H55V0H0Z" fill={c} stroke={ink} stroke-width="3"/>
        <path d="M8-52V-8M19-47H44" stroke="#E5D7BC" stroke-width="3"/>
      </g>
    </g>:
    k==="ball"?<><circle cy="-24" r="24" fill={c} stroke={ink} stroke-width="3"/><path d="M-24-24H24M0-48Q-20-24 0 0" stroke="#E5D7BC" fill="none" stroke-width="3"/></>:
    k==="pendant"?<><path d="M-12-34q-18-40 12-40t12 40L0-10Z" stroke="#C0BCA4" fill="none" stroke-width="3"/><path d="M0-26L12-12L0 2L-12-12Z" fill="#C0BCA4" stroke={ink} stroke-width="2"/></>:
    k==="lamp"?<><path d="M0 0V-111M-25 0H25" stroke="#B7B7AB" stroke-width="5"/><path d="M-48-110L-32-168H32L48-110Z" fill="#B6ACA1" stroke={ink} stroke-width="3"/></>:
    k==="tree"?<><path d="M0 0V-221" stroke="#5D5049" stroke-width="25"/><path d="M-74-164Q-116-260-43-289Q-3-338 49-281Q120-260 71-164Z" fill="#3F7A62" stroke="#315A52" stroke-width="4"/></>:
    k==="cup"?<><path d="M-20-40H20L15-4H-15Z" fill="#CFDBD2" stroke={ink} stroke-width="2"/><path d="M20-31Q45-35 34-13L18-10" fill="none" stroke="#CFDBD2" stroke-width="5"/></>:
    <g>
      <path d="M-39-35H39V0H-39Z" fill={c} stroke={ink} stroke-width="3"/>
      <path d="M-39-36L-29-49H31L39-36Z" fill="#44322E" stroke={ink} stroke-width="3"/>
      <path d="M-32-19H32M-31-11H31" fill="none" stroke="#715048" stroke-width="1.5"/>
      <g data-box-lid={prop.id} transform={`rotate(${open*100} 36 -38)`}>
        <path d="M-39-38H39V-48H-39Z" fill={c} stroke={ink} stroke-width="3"/>
        <path d="M-5-38H5V-33H-5Z" fill="#D3B278" stroke={ink} stroke-width="1.5"/>
      </g>
    </g>}
  </g>;
}

export function propAnchor(scene:Item,prop:Item,w:number,h:number,unit:number) {
  const support=scene.props.find((p:Item)=>p.id===prop.support_id);
  const anchor=support?{x:support.x*w,y:support.y*h-(support.type==="table"?122:support.type==="chair"?67:119)*unit}:{x:prop.x*w,y:prop.y*h};
  return prop.reveal_from_id?{x:anchor.x,y:anchor.y-37*unit}:anchor;
}

function Background({scene,w,h,t,prefix}:Item) {
  const night=scene.lighting==="night",inside=["home","bedroom","school","workshop","castle"].includes(scene.environment);
  const sky=night?"#23384A":scene.environment==="space"?"#182343":scene.environment==="desert"?"#DDAA7E":"#8EBCC5";
  const ground=night?"#1B2A39":scene.environment==="beach"?"#D7BE91":inside?"#5E5962":"#5D886D";
  return <g>
    <defs><linearGradient id={prefix+"sky"} x2="0" y2="1"><stop stop-color={sky}/><stop offset="1" stop-color={night?"#344856":"#E5E3CF"}/></linearGradient>
    <radialGradient id={prefix+"shade"}><stop offset=".4" stop-color="#081726" stop-opacity="0"/><stop offset="1" stop-color="#081726" stop-opacity=".48"/></radialGradient></defs>
    <rect width={w} height={h} fill={`url(#${prefix}sky)`}/>
    {inside?<g>
      <rect width={w} height={h*.81} fill={night?"#2B3E4B":scene.environment==="workshop"?"#6D7A81":"#9D9292"}/>
      {[.06,.30,.55,.79].map(v=><path key={v} d={`M${w*v} 0V${h*.81}`} stroke="#D9DDD0" stroke-opacity=".045" stroke-width="2"/>)}
      <rect x={w*.07} y={h*.16} width={w*.28} height={h*.37} fill={sky} stroke="#6C838F" stroke-width={w*.006}/>
      <path d={`M${w*.21} ${h*.16}V${h*.53}M${w*.07} ${h*.345}H${w*.35}`} stroke="#8AA0A7" stroke-width={w*.005}/>
      <circle cx={w*.28} cy={h*.24} r={Math.min(w,h)*.035} fill={night?"#CBDEDD":"#F2DEAF"}/>
      {[.035,.335].map((v,i)=><path key={v} d={`M${w*v} ${h*.13}q${w*(i?-.04:.04)} ${h*.2} 0 ${h*.44}h${w*.055}q${w*.025}-${h*.24} 0-${h*.44}Z`} fill="#465865"/>)}
      <path d={`M${w*.09} ${h*.2}L${w*.35} ${h*.2}L${w*.85} ${h}L${w*.25} ${h}Z`} fill="#D2E9DC" opacity={night?.055:.08}/>
      {scene.environment==="school"||scene.environment==="workshop"?<><rect x={w*.43} y={h*.2} width={w*.44} height={h*.27} fill="#3C5F58" stroke="#B5ADA0" stroke-width="7"/><path d={`M${w*.49} ${h*.3}h${w*.24}m-${w*.24} ${h*.07}h${w*.31}`} stroke="#CAD5C8" stroke-width="3" opacity=".5"/></>:<rect x={w*.45} y={h*.21} width={w*.18} height={h*.13} fill="#3D5666" stroke="#8D9B9B" stroke-width={w*.004}/>}
    </g>:<g>
      <circle cx={w*.8} cy={h*.17} r={Math.min(w,h)*.055} fill={night?"#D2DDD4":"#EFDFAB"}/>
      <g transform={`translate(${Math.sin(t*.15)*w*.012} 0)`} fill="#D7E3DE" opacity=".55"><ellipse cx={w*.23} cy={h*.23} rx={w*.11} ry={h*.02}/><ellipse cx={w*.26} cy={h*.21} rx={w*.06} ry={h*.035}/></g>
      <path d={`M0 ${h*.65}Q${w*.2} ${h*.3} ${w*.5} ${h*.67}T${w} ${h*.62}V${h}H0Z`} fill={scene.environment==="beach"?"#5B9EAA":"#628C8A"}/>
      {scene.environment==="city"?[.04,.22,.45,.7,.88].map((x,i)=><g key={x}><rect x={w*x} y={h*(.45-(i%2)*.1)} width={w*.12} height={h*.35} fill={i%2?"#4F667D":"#637E8C"}/>{[0,1,2].map(j=><path key={j} d={`M${w*(x+.025)} ${h*(.49+j*.07)}h${w*.07}`} stroke="#B8B7A2" stroke-width="8"/>)}</g>):[.06,.90].map(x=><Prop key={x} prop={{id:"tree-"+x,type:"tree"}} x={w*x} y={h*.81} unit={Math.min(w,h)/650}/>)}
    </g>}
    <path d={`M0 ${h*.79}Q${w*.4} ${h*.77} ${w} ${h*.81}V${h}H0Z`} fill={ground}/>
    {[0,1,2,3].map(i=><path key={i} d={`M0 ${h*(.84+i*.045)}H${w}`} stroke="#D6E3D8" stroke-opacity=".07" stroke-width="1.5"/>)}
  </g>;
}

function cameraAt(scene:Item,states:Item[],t:number,w:number,h:number,rigHeight:number):Item {
  const keys=scene.camera;
  const before=keys.filter((c:Item)=>c.time<=t).at(-1)||keys[0],after=keys.find((c:Item)=>c.time>t)||before;
  const cam=(key:Item)=>{
    const a=states.find(a=>a.character_id===key.focus_id);
    const prop=scene.props.find((p:Item)=>p.id===key.focus_id);
    const interaction=scene.actions.some((v:Item)=>["pick_up","put_down","open_door","close_door"].includes(v.type)
      &&t>=v.start-.2&&t<v.end+.2
      &&!(v.type==="pick_up"&&scene.props.some((p:Item)=>p.id===v.target_id&&p.reveal_from_id)));
    const zoom=interaction?1:({wide:1,medium:1.3,close:2.1,detail:2.6}[key.shot as string]||1);
    const pose=a?poseAmount(a,t):0,sitting=clamp(pose/.28)*(1-clamp((pose-.28)/.72));
    const revealAnchor=prop&&(prop.type==="box"||prop.reveal_from_id)
      ?propAnchor(scene,prop,w,h,Math.min(w,h)/880):null;
    let x=a?a.x*w:revealAnchor?.x??(prop?prop.x*w:w/2);
    let y=a?a.y*h-rigHeight*(zoom>1.5?.77-sitting*.145:.44)
      :revealAnchor?revealAnchor.y-h*(key.shot==="detail"?.025:.075):(prop?prop.y*h-h*.18:h/2);
    if(zoom===1){x=w/2;y=h/2;}
    x+=key.pan*w;
    return {x:clamp(x,w/(2*zoom),w-w/(2*zoom)),y:clamp(y,h/(2*zoom),h-h/(2*zoom)),zoom};
  };
  const a=cam(before),b=cam(after),p=before===after?0:progress(t,before.time,after.time);
  return {x:mix(a.x,b.x,p),y:mix(a.y,b.y,p),zoom:mix(a.zoom,b.zoom,p)};
}

function Scene({story,scene,t,w,h,opacity=1}:Item) {
  const map=chars(story),unit=Math.min(w,h)/880;
  const states=scene.actors.map((a:Item,i:number)=>actorState(scene,a,t,i));
  const rigHeight=Math.min(h*.66,w*(states.length>2?.27:states.length===2?.52:.72));
  const scale=rigHeight/455,cam=cameraAt(scene,states,t,w,h,rigHeight);
  const prefix=scene.id+"-";
  const held=new Map(scene.props.map((p:Item)=>[p.id,propState(scene,p,t)]));
  const visibleProps=scene.props.filter((p:Item)=>!p.reveal_from_id||(held.get(p.reveal_from_id)?.open??0)>=.65);
  return <g opacity={opacity}>
    <g transform={`translate(${w/2} ${h/2}) scale(${cam.zoom}) translate(${-cam.x} ${-cam.y})`}>
      <Background {...{scene,w,h,t,prefix}}/>
      {visibleProps.toSorted((a:Item,b:Item)=>Number(!!a.support_id)+Number(!!a.reveal_from_id)-Number(!!b.support_id)-Number(!!b.reveal_from_id)).map((p:Item)=>!held.get(p.id)?.held&&<Prop key={p.id} prop={p} {...propAnchor(scene,p,w,h,unit)} unit={p.type==="bed"?Math.min(w*.00095,h*.0014):unit} open={held.get(p.id)?.open}/>)}
      {states.toSorted((a:Item,b:Item)=>a.y-b.y).map((state:Item)=>{
        const c=map.get(state.character_id),speech=(scene.audio||[]).find((a:Item)=>a.speaker_id===c?.id&&a.track==="dialogue"&&t>=a.start&&t<a.start+a.duration);
        const envelope=speech?.envelope||[],frame=speech?(t-speech.start)*60:0;
        const mouth=mix(envelope[Math.floor(frame)]||0,envelope[Math.ceil(frame)]||0,frame%1);
        const word=speech?.words?.find((v:Item)=>t>=v.start_seconds&&t<v.end_seconds)?.text||"";
        const target=scene.props.find((p:Item)=>p.id===state.target),s=scale*state.scale*c?.appearance.body_scale;
        if(target&&!(state.reachAction==="open_book"&&held.get(target.id)?.held===state.character_id)){
          const anchor=propAnchor(scene,target,w,h,unit),tx=(anchor.x-state.x*w+(target.type==="door"?53*unit:0))/s,ty=(anchor.y-state.y*h-(target.type==="door"?173*unit:0))/s;
          state.crouch=state.reach*clamp((ty+140)/140);state.bodyOffset=60*state.crouch;state.bend=42*state.crouch;
          const angle=rad(state.bend),y=ty-state.bodyOffset+112;
          state.localTarget={x:tx*Math.cos(angle)+y*Math.sin(angle),y:-112-tx*Math.sin(angle)+y*Math.cos(angle)};
        }
        return <g key={c?.id}><Biped character={c} state={state} t={t} x={state.x*w} y={state.y*h} scale={s} prefix={prefix+c?.id} mouth={mouth} viseme={/[وou]/i.test(word)?"round":"open"}/>
          {visibleProps.filter((p:Item)=>held.get(p.id)?.held===state.character_id).map((p:Item)=>{
            const {hand}=armPoints(state,1);
            const angle=rad(state.bend||0);
            return <Prop key={p.id} prop={p} x={state.x*w+(hand.x*Math.cos(angle)-(hand.y+112)*Math.sin(angle))*s}
              y={state.y*h+(-112+hand.x*Math.sin(angle)+(hand.y+112)*Math.cos(angle)+(state.bodyOffset||0))*s} unit={s*.7}
              open={held.get(p.id)?.open}/>;
          })}</g>;
      })}
      <rect width={w} height={h} fill={`url(#${prefix}shade)`} opacity=".45"/>
      {scene.lighting==="memory"&&<rect width={w} height={h} fill="#C9A379" opacity=".15"/>}
    </g>
  </g>;
}

export function storyFrame(story:Item,time:number,width:number,height:number) {
  const t=clamp(time,0,story.duration-1/300),index=Math.max(0,story.scenes.findLastIndex((s:Item)=>s.start<=t));
  const scene=story.scenes[index],local=t-scene.start,fade=scene.transition!=="cut"&&index>0?progress(local,0,.4):1;
  return <svg xmlns="http://www.w3.org/2000/svg" width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
    <rect width={width} height={height} fill="#172C3E"/>
    {fade<1&&<Scene story={story} scene={story.scenes[index-1]} t={story.scenes[index-1].duration-.001} w={width} h={height}/>}
    <Scene {...{story,scene}} t={local} w={width} h={height} opacity={fade}/>
    {scene.transition==="dip"&&local<.4&&<rect width={width} height={height} fill="#142333" opacity={Math.sin(Math.PI*clamp(local/.4))}/>}
  </svg>;
}

export function createStoryRenderer(element:HTMLElement,story:Item,width:number,height:number) {
  return (time:number)=>render(storyFrame(story,time,width,height),element);
}
