// One seekable character rig, shared by every shot. All animation is a function of time.
const clamp=(x,a=0,b=1)=>Math.min(b,Math.max(a,x));
const smooth=(a,b,t)=>{const q=clamp((t-a)/(b-a));return q*q*(3-2*q)};
const lerp=(a,b,q)=>a+(b-a)*q;
const path=(d,fill,stroke='#17202b',w=3,extra='')=>`<path d="${d}" fill="${fill}" stroke="${stroke}" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" ${extra}/>`;
const ellipse=(cx,cy,rx,ry,fill,extra='')=>`<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="${fill}" ${extra}/>`;
const defs=`<defs><clipPath id="sleep-crop"><rect x="0" y="0" width="1920" height="750"/></clipPath>
 <linearGradient id="wall" x2="1" y2="1"><stop stop-color="#344756"/><stop offset=".55" stop-color="#273440"/><stop offset="1" stop-color="#18212c"/></linearGradient>
 <linearGradient id="floor" x2="0" y2="1"><stop stop-color="#28323a"/><stop offset="1" stop-color="#101c28"/></linearGradient>
 <linearGradient id="wood" x2="1" y2="0"><stop stop-color="#242a33"/><stop offset=".48" stop-color="#51464a"/><stop offset="1" stop-color="#262831"/></linearGradient>
 <linearGradient id="skin" x1="0" x2="1" y1="0" y2=".4"><stop stop-color="#e7b79c"/><stop offset=".45" stop-color="#ca9a85"/><stop offset="1" stop-color="#8b716e"/></linearGradient>
 <linearGradient id="neck" x2="1" y2="1"><stop stop-color="#a27c70"/><stop offset="1" stop-color="#deb29a"/></linearGradient>
 <linearGradient id="cloth" x2="1" y2=".5"><stop stop-color="#448b8b"/><stop offset=".5" stop-color="#306b73"/><stop offset="1" stop-color="#1b444f"/></linearGradient>
 <linearGradient id="quilt" x2="0" y2="1"><stop stop-color="#8b7e96"/><stop offset=".2" stop-color="#69617d"/><stop offset="1" stop-color="#3a3b55"/></linearGradient>
 <linearGradient id="pillow" x2="1" y2="1"><stop stop-color="#b8c8ca"/><stop offset="1" stop-color="#718a98"/></linearGradient>
 <linearGradient id="glass" x2="1" y2="1"><stop stop-color="#547888"/><stop offset="1" stop-color="#122d44"/></linearGradient>
 <radialGradient id="shade"><stop offset=".4" stop-color="#030d19" stop-opacity="0"/><stop offset="1" stop-color="#030d19" stop-opacity=".66"/></radialGradient>
 <linearGradient id="moonbeam" x1="0" y1="0" x2=".8" y2="1"><stop stop-color="#a9dce3" stop-opacity=".16"/><stop offset="1" stop-color="#a9dce3" stop-opacity="0"/></linearGradient>
 <linearGradient id="doorlight" x2="0" y2="1"><stop stop-color="#e1b97e" stop-opacity=".15"/><stop offset="1" stop-color="#e1b97e" stop-opacity="0"/></linearGradient>
 <radialGradient id="iris"><stop stop-color="#78615b"/><stop offset=".6" stop-color="#4d4042"/><stop offset="1" stop-color="#18212b"/></radialGradient>
</defs>`;

function room(t){
 const sway=Math.sin(t*.6)*5;
 let s=`<rect width="1920" height="1080" fill="url(#wall)"/>`;
 // Painted wall panels and receding timber floor.
 for(let i=0;i<14;i++)s+=path(`M${i*160} 110V790`,'none','#c1d0ce',1,'opacity=".025"');
 s+=path('M0 784H1920V1080H0Z','url(#floor)','#192735',2);
 s+=path('M0 785H1920M0 802H1920','none','#65717b',3,'opacity=".3"');
 for(let i=-5;i<14;i++)s+=path(`M${850+i*95} 800L${850+i*260} 1080`,'none','#79909b',1.5,'opacity=".12"');
 for(let i=0;i<4;i++)s+=path(`M0 ${833+i*i*15}H1920`,'none','#81929b',1,'opacity=".08"');
 // Moonlit window, sill, curtain rod, layered fabric.
 s+=`<rect x="86" y="168" width="376" height="443" rx="4" fill="#172634" stroke="#7d919c" stroke-width="9"/><rect x="108" y="188" width="332" height="396" fill="url(#glass)"/>`;
 s+=ellipse(354,252,41,41,'#bbd3d7');s+=ellipse(369,241,39,39,'#426577');
 s+=path('M108 540L178 489L226 514L292 479L354 508L440 473V584H108Z','#152b3d','none');
 s+=path('M274 188V584M108 382H440','none','#748c98',11);s+=path('M80 604H469','none','#9aadb0',10);
 s+=path('M44 151H505','none','#172330',12);
 s+=path(`M53 167C74 289 41 443 62 628Q99 644 144 625C118 485 156 334 143 167Z`,'#384555','#192b3a',3);
 s+=path(`M104 169C116 298 ${83+sway} 426 104 621M72 171C91 334 60 492 79 620`,'none','#617481',3,'opacity=".4"');
 s+=path(`M408 166C398 324 ${450+sway} 465 417 631Q459 643 502 624C473 464 504 314 493 167Z`,'#384555','#192b3a',3);
 s+=path(`M438 171C432 312 ${481+sway} 473 452 629M474 170C461 331 496 480 478 625`,'none','#687a88',3,'opacity=".3"');
 s+=path('M116 206L419 190L1135 1010L518 1080Z','url(#moonbeam)','none');
 s+=path('M174 804L401 794L1003 1011L711 1052Z','#8bbac3','none',0,'opacity=".055"');
 // Door always on screen-right: panel geometry and hardware never move.
 s+=`<rect x="1457" y="232" width="306" height="579" fill="#0c1520" stroke="#56616a" stroke-width="8"/><rect x="1475" y="247" width="267" height="554" fill="url(#wood)" stroke="#19232e" stroke-width="4"/>`;
 for(const [y,h] of [[271,233],[529,241]])s+=`<rect x="1500" y="${y}" width="215" height="${h}" rx="3" fill="#29303a" stroke="#6a5c5a" stroke-width="3"/><rect x="1512" y="${y+12}" width="190" height="${h-24}" fill="#33343d" stroke="#1f2833" stroke-width="2"/>`;
 s+=`<rect x="1693" y="492" width="19" height="72" rx="8" fill="#696157" stroke="#b6a28a" stroke-width="1.5"/>`;
 s+=path('M1699 518h-39q-8 0-8 6t8 6h39Z','#aa9980','#433e3c',2);
 s+=path('M1478 802H1739','none','#e4bd85',3);s+=path('M1478 804L1739 804L1845 1001L1352 1001Z','url(#doorlight)','none');
 // Framed landscape and bedside furniture.
 s+=`<rect x="1098" y="270" width="196" height="138" fill="#192632" stroke="#5d676c" stroke-width="8"/><rect x="1110" y="282" width="171" height="113" fill="#4c5a65"/>`;
 s+=path('M1110 367L1172 310L1209 351L1246 326L1281 369V395H1110Z','#263e4d','none');
 s+=`<rect x="151" y="688" width="165" height="156" rx="5" fill="url(#wood)" stroke="#1a2734" stroke-width="4"/><path d="M143 684H326V701H143Z" fill="#56636b"/><rect x="164" y="713" width="139" height="51" fill="#39424e" stroke="#1c2835" stroke-width="2"/><circle cx="233" cy="737" r="5" fill="#a6987f"/><path d="M173 845v51m120-51v51" stroke="#26303d" stroke-width="11"/>`;
 s+=path('M236 675V591M212 675h48','none','#a2a3a1',7);s+=path('M183 588L199 523H276L294 588Z','#8792a0','#394958',3);
 // Analog clock set to midnight, unlit lamp.
 s+=ellipse(178,655,27,27,'#243241','stroke="#8b9ba3" stroke-width="4"');
 for(let i=0;i<12;i++){let a=i*Math.PI/6;s+=path(`M${178+Math.sin(a)*21} ${655-Math.cos(a)*21}L${178+Math.sin(a)*18} ${655-Math.cos(a)*18}`,'none','#b9c4c5',2)}
 s+=path('M178 655V640M178 655V635','none','#dbe1dc',2);s+=ellipse(178,655,2.5,2.5,'#dbe1dc');
 // Bed with a substantial headboard, feet, mattress and separate pillow.
 s+=path('M331 745V475Q331 453 355 453H407Q431 453 431 477V745Z','url(#wood)','#1c2834',4);
 s+=path('M350 482V724M410 482V724','none','#7c6e70',3,'opacity=".4"');
 s+=path('M382 749H1240V819H382Z','url(#wood)','#172331',4);s+=path('M403 817V901H436V817M1182 817V901H1211V817','url(#wood)','#172331',3);
 s+=path('M398 644Q408 621 455 623L1175 651Q1225 656 1236 697V747H399Z','url(#pillow)','#354654',4);
 s+=path('M400 719L1234 739V761L399 748Z','#7b929f','#314655',2);
 s+=path('M393 639Q396 601 437 600L602 617Q638 624 638 656Q636 680 612 689L429 668Q401 665 393 639Z','url(#pillow)','#4b6575',3);
 s+=path('M411 638Q434 620 466 628L603 644','none','#dae1dc',3,'opacity=".32"');
 return s;
}

function hand(x,y,a=0){return `<g transform="translate(${x} ${y}) rotate(${a})">${path('M-14-22Q-22-11-18 9L-10 32Q-4 41 1 33L0 12L7 35Q12 41 16 34L12 8Q18 22 23 17L15-11Q14-22 3-26Q-9-32-14-22Z','url(#skin)','#493e45',2.1)}${path('M-10 8L-4 22M1 7L7 24M-13-8L2-3','none','#9d7971',1.5)}</g>`}

function arm(side,pose,t){
 const x=side*78,y=-213;
 let ex=side*105,ey=-106,hx=side*104,hy=4;
 if(side===1){const q=1-smooth(16.3,18,t);ex=lerp(ex,137,q);ey=lerp(ey,-142,q);hx=lerp(hx,23,q);hy=lerp(hy,-164,q);}
 if(side===-1){const q=smooth(17,18.5,t)*(1-smooth(23.3,24.3,t));ex=lerp(ex,-119,q);ey=lerp(ey,-82,q);hx=lerp(hx,-166,q);hy=lerp(hy,20,q);}
 const a=Math.atan2(hy-ey,hx-ex)*180/Math.PI-90;
 return path(`M${x-18} ${y}Q${ex-26} ${ey-35} ${ex-19} ${ey+8}L${hx-17} ${hy-18}Q${hx} ${hy-9} ${hx+17} ${hy-20}L${ex+19} ${ey-7}Q${ex+22} ${ey-38} ${x+20} ${y-4}Z`,'url(#cloth)','#172e3b',3)+path(`M${hx-16} ${hy-23}L${hx+15} ${hy-24}`,'none','#70a1a0',3)+hand(hx,hy,a);
}

function face(t,awake,mouth,pain,gaze,tilt){
 const breath=Math.sin(t*2.5)*1.2;
 const blinkTimes=[5.3,8.6,14.8,18.7,23.3,27.2];
 let blink=0;for(const at of blinkTimes)blink=Math.max(blink,clamp(1-Math.abs(t-at)/.12));
 const eye=awake*(1-blink),wide=lerp(.7,1,pain>.3?.4:awake);
 const turn=smooth(24,26.7,t)*.9;
 let out=`<g transform="translate(${turn*8} ${breath}) rotate(${tilt} 0 -300)">`;
 out+=path('M-85-388Q-93-452-19-465Q59-480 92-420Q111-390 99-316L119-165Q78-106 39-186L-54-184Q-105-176-103-234Z','#121c29','#101b28',4);
 out+=path('M-75-395Q-86-343-78-284Q-65-260-51-283L-52-366M77-402Q94-318 89-265L103-208','none','#3f4e5b',5,'opacity=".65"');
 // Neck, ears and softly modeled face.
 out+=path('M-29-279L-32-226Q-5-204 33-225L27-279Z','url(#neck)','#614e51',2.5);
 out+=ellipse(-75,-332,15,26,'#b78e80','stroke="#715c5b" stroke-width="2"');
 out+=ellipse(77,-331,13,24,'#a67f75','stroke="#6a5657" stroke-width="2"');
 out+=path('M-71-398Q-51-441 2-439Q59-441 76-398L76-341Q73-289 43-266Q11-241-9-253Q-58-273-70-326Z','url(#skin)','#513f47',2.7);
 out+=path('M49-421Q82-379 63-323Q53-287 19-258Q43-258 64-286Q82-315 76-375L74-401Z','#7d6870','none',0,'opacity=".33"');
 out+=path('M-64-386Q-55-410-33-417','none','#f1cbb0',4,'opacity=".45"');
 const brow=-363-8*awake;
 out+=path(`M-61 ${brow+5+pain*6}Q-40 ${brow-9-pain*5} -17 ${brow+pain*7}`,'none','#2b2730',7);
 out+=path(`M18 ${brow+pain*7}Q39 ${brow-10-pain*5} 62 ${brow+5+pain*5}`,'none','#2b2730',6.5);
 for(const side of [-1,1]){
  const cx=side*39,cy=-342;
  if(eye>.09){
   out+=`<g transform="translate(${cx+turn*12} ${cy}) scale(${side===1?1-turn*.23:1} ${eye*wide})">`;
   out+=path('M-24 0Q-10-20 6-18Q20-16 25 0Q8 13-9 11Q-20 8-24 0Z','#d6d8ce','#392d37',2.8);
   out+=ellipse(gaze*7, -1,11.3,14,'url(#iris)');out+=ellipse(gaze*7,-.5,5.5,9,'#101b26');
   out+=ellipse(gaze*7-3,-6,3.2,3.2,'#edf1df');out+=ellipse(gaze*7+4,4,1.2,1.8,'#cbd8d6');
   out+=path('M-24 0Q-12-21 5-18Q20-16 25 0M-23-1L-28-6','none','#2b2632',4);
   out+='</g>';
   out+=path(`M${cx-20} -320Q${cx} -311 ${cx+19} -320`,'none','#956d69',1.7,'opacity=".6"');
  }else out+=path(`M${cx-23} -341Q${cx} -326 ${cx+23} -342`,'none','#312b36',4);
 }
 out+=`<g transform="translate(${turn*14} 0)">`;
 out+=path('M6-341Q1-318-3-309Q4-303 14-309','none','#9d746a',2.3);
 out+=path('M-3-305Q5-300 15-305','none','#e6b89e',2.5,'opacity=".7"');
 // Rounded/flat visemes follow actual syllabic energy; closed in silence.
 if(mouth>.12){const w=12+mouth*8,h=2+mouth*10;out+=ellipse(6,-286,w,h,'#56323d','stroke="#8c555c" stroke-width="2"');out+=path(`M${7-w*.65} ${-286-h*.6}Q6 ${-288-h*.7} ${6+w*.65} ${-286-h*.6}`,'none','#dac6b5',2.3);out+=ellipse(7,-283+h*.3,w*.55,h*.25,'#a66a71');}
 else out+=path(`M-13-285Q5 ${-290+pain*5} 25-284M-4-280Q7-277 17-280`,'none','#8b535b',2.8);
 out+='</g>';
 // Hairline and two stable face-framing locks.
 out+=path('M-78-367Q-88-434-28-451Q8-466 45-445Q81-435 85-394Q54-408 24-433L5-443Q-20-423-51-417Q-68-406-78-367Z','#182331','#111e2c',3);
 out+=path('M5-443Q-22-437-43-419M16-448Q48-439 64-419','none','#455360',3,'opacity=".8"');
 out+=path('M66-417Q85-361 69-308Q87-325 88-359Q89-397 74-420Z','#1a2735','#152331',2);
 out+=path(`M-65-414Q-82-367-66-306Q-60-283 ${-71+Math.sin(t*1.6)*1.5} -264`,'none','#1b2633',8);
 out+=path('M-63-417Q-73-369-61-335','none','#526270',2,'opacity=".6"');
 if(pain>.3)out+=ellipse(55,-313+smooth(17.7,20,t)*45,3.3,6,'#a6d1d4','opacity=".72"');
 return out+'</g>';
}

function character(t,{x=780,y=735,rotation=0,standing=0,awake=1,mouth=0,pain=0,gaze=0,tilt=0,pose='chest',scale=1}={}){
 let s=`<g transform="translate(${x} ${y}) scale(${scale}) rotate(${rotation})">`;
 // Legs below the long kameez. Two separate silhouettes retain floor contact.
 s+=path(`M-59 1L-58 ${115+standing*65}Q-63 ${151+standing*52}-33 ${154+standing*50}L-13 ${145+standing*58}L-4 4Z`,'#26515c','#142c3b',3);
 s+=path(`M7 1L15 ${133+standing*64}Q18 ${154+standing*52} 47 ${155+standing*50}L64 ${145+standing*58}L62 0Z`,'#1e444f','#142c3b',3);
 const foot=155+standing*50;
 s+=path(`M-58 ${foot-7}L-58 ${foot+11}Q-74 ${foot+15}-77 ${foot+25}Q-59 ${foot+31}-25 ${foot+21}L-22 ${foot-8}Z`,'url(#skin)','#4e4950',2.5);
 s+=path(`M21 ${foot-5}L20 ${foot+12}Q27 ${foot+22} 79 ${foot+24}Q83 ${foot+15} 59 ${foot+10}L53 ${foot-5}Z`,'url(#skin)','#4e4950',2.5);
 // Rear hair extends below shoulders, body never changes costume.
 s+=path('M-79-324L-108-154Q-96-109-53-107L61-112Q104-130 99-164L86-330Z','#14202d','#132130',3);
 s+=arm(-1,pose,t);
 s+=path('M-76-228Q-46-242-32-230Q-2-212 31-230Q60-242 79-222Q74-136 66-72L82 31Q9 60-80 33L-64-88Z','url(#cloth)','#16313f',3.5);
 s+=path('M-31-231Q-5-210 31-230L22-209Q-2-198-22-208Z','#7aabab','#274f5c',2);
 s+=path('M-3-206L-3-151','none','#9bbeb1',2);for(let j=0;j<3;j++)s+=ellipse(-3,-193+j*15,2.4,2.4,'#b9c5b5');
 s+=path('M-47-186Q-56-102-33-15M43-172Q31-101 47 18M-64 25Q10 46 70 23','none','#659898',2.6,'opacity=".55"');
 s+=path('M-53-133Q-55-66-71 17L-39 25Q-45-57-36-102Z','#163f4c','none',0,'opacity=".35"');
 s+=face(t,awake,mouth,pain,gaze,tilt);
 s+=arm(1,pose,t);
 return s+'</g>';
}

function blanket(t){
 const q=smooth(17,20.8,t),left=lerp(568,936,q),top=lerp(670,734,q);
 let s=path(`M${left} ${top}Q${left+100} ${top-37} ${left+203} ${top-3}L1204 682Q1230 693 1230 732L1240 827Q1122 855 1024 819L${left} ${top+113}Z`,'url(#quilt)','#32374e',3);
 s+=path(`M${left+14} ${top+14}Q${left+115} ${top-8} 1158 716M${left+50} ${top+34}Q${left+150} ${top+15} 1187 746M${left+80} ${top+67}Q${left+150} ${top+47} 1209 790`,'none','#a59aaf',3,'opacity=".25"');
 for(let i=0;i<9;i++)s+=path(`M${lerp(left+30,1190,i/9)} ${top+16}l-10 92`,'none','#bbb0bd',1,'opacity=".15"');
 return s;
}

function memory(t){
 const p=smooth(15.5,16.2,t),pull=smooth(16.3,18,t);
 let s=`<rect width="1920" height="1080" fill="#453f3d"/><rect x="1150" y="90" width="500" height="870" fill="#202a30"/><path d="M1164 96L1469 176V955L1164 968Z" fill="#70605a" stroke="#242c31" stroke-width="8"/>`;
 s+=path('M0 827L1920 824V1080H0Z','#514844','none');
 s+=`<g transform="translate(${1100+pull*240} ${320+pull*15}) rotate(${-8+pull*12})">${path('M-400-40Q-120-45 0 0L-5 91Q-210 104-410 78Z','#5c6669','#34363b',5)}${hand(16,78,115)}</g>`;
 s+=`<g transform="translate(700 710) rotate(-13)">${path('M-800 88Q-405-56-98-62L-52 108Q-306 216-750 278Z','url(#cloth)','#213d47',5)}${path('M-106-53Q-45-102 48-99L176-58Q212-43 188-26L77-44L212-12Q246 9 218 23L65 6L201 48Q230 70 198 82L35 51L137 98Q153 124 113 123L-22 90Q-65 62-96 104Z','url(#skin)','#6d5352',4)}
 ${path('M-45-64Q-40-111 15-100L98-70Q119-49 99-35L19-57Q1-56-12-34','url(#skin)','#6d5352',3)}
 ${path('M-12-25Q19-108 71-75Q106-52 67-6Q43 20 4 60','none','#c1b9a0',4)}
 ${path('M46 3L70 31L52 55L27 31Z','#bcb9aa','#645b55',3)}${path('M50 14L43 28L52 35L44 43','none','#635c58',3)}</g>`;
 s+=`<rect width="1920" height="1080" fill="#b49670" opacity=".12"/><rect width="1920" height="1080" fill="url(#shade)"/>`;
 return s;
}

export function renderFilm(t,envelope=[],options={}){
 const durationSeconds=Math.max(1,Number(options.durationSeconds)||30);
 const animationTime=Math.max(0,Math.min(30,t*30/durationSeconds));
 let x=780,y=735,rotation=-74*(1-smooth(2.3,3.35,animationTime)),stand=smooth(21.2,23.8,animationTime),awake=smooth(2.1,2.3,animationTime),pose=animationTime<17?'chest':'support';
 const breath=Math.sin(animationTime*3.6)*1.5*(animationTime>2.3?1:0.25);
 if(animationTime>=17){x=lerp(780,951,smooth(17,20,animationTime));y=lerp(735,713,smooth(17,20,animationTime));}
 if(animationTime>=21.2){x=lerp(951,1080,stand);y=lerp(713,688,stand);}
 if(animationTime>=23.8)pose='rest';
 let mouth=0;
 // The supplied envelope is sampled at 60 Hz over the whole episode, so every scene dialogue can animate the same rig.
 if(envelope.length){
  const sample=Math.max(0,t*60),lower=Math.floor(sample),upper=Math.ceil(sample),blend=sample-lower;
  mouth=clamp((envelope[lower]||0)*(1-blend)+(envelope[upper]||0)*blend);
 }
 let pain=smooth(14,15.4,animationTime)*(1-smooth(23.4,25,animationTime)*.6);
 let gaze=animationTime<4?0:animationTime<7?Math.sin(animationTime*2)*.5:animationTime<14?-.1:smooth(14,15,animationTime)*.8;
 if(animationTime>24)gaze=.9;
 let tilt=animationTime<7?-3:lerp(-3,4,smooth(13.7,15.5,animationTime));
 let camera={cx:960,cy:540,z:1.03};
 if(animationTime<2.3)camera={cx:720,cy:614,z:lerp(1.31,1.38,animationTime/2.3)};
 else if(animationTime<7)camera={cx:759,cy:458,z:lerp(1.53,1.72,smooth(2.3,7,animationTime))};
 else if(animationTime<15.5)camera={cx:785,cy:410,z:lerp(2.62,2.91,smooth(7,15.5,animationTime))};
 else if(animationTime<18.1)camera={cx:960,cy:540,z:1};
 else if(animationTime<21.2)camera={cx:1045,cy:560,z:1.2};
 else if(animationTime<24.6)camera={cx:1090,cy:585,z:1.20};
 else camera={cx:1330,cy:460,z:lerp(1.47,1.65,smooth(24.6,30,animationTime))};
 let s=defs+`<rect width="1920" height="1080" fill="#0e1823"/><g transform="translate(960 540) scale(${camera.z}) translate(${-camera.cx} ${-camera.cy})">`;
 s+=room(animationTime);
 if(animationTime>19)s+=ellipse(x+16,929-stand*8,92,13,'#071421','opacity=".48"');
 s+=`<g ${animationTime<3.35?'clip-path="url(#sleep-crop)"':''}>`+character(animationTime,{x,y:y+breath,rotation,standing:stand,awake,mouth,pain,gaze,tilt,pose})+'</g>';
 if(animationTime<21.2)s+=blanket(animationTime);
 else s+=blanket(21.2);
 s+='</g>';
 if(animationTime>=15.5&&animationTime<18.1){const op=smooth(15.5,15.8,animationTime)*(1-smooth(17.7,18.1,animationTime));s+=`<g opacity="${op}">${memory(animationTime)}</g>`;}
 s+=`<rect width="1920" height="1080" fill="url(#shade)" opacity=".35"/><rect width="1920" height="100" fill="#080f18"/><rect y="980" width="1920" height="100" fill="#080f18"/>`;
 return `<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080">${s}</svg>`;
}
