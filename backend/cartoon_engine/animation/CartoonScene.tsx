import React from "react";
type Appearance = {
  skin_color?: string;
  hair_color?: string;
  shirt_color?: string;
  pants_color?: string;
  shoe_color?: string;
  hair_style?: string;
};

type CartoonCharacter = {
  id: string;
  name: string;
  species?: string;
  appearance?: Appearance;
};

type StoryScene = {
  id?: string;
  scene_title?: string;
  environment?: string;
  expression?: string;
  motion?: string;
  camera_move?: string;
  speaker_id?: string;
  action?: string;
};

export type CartoonSceneProps = {
  durationSeconds: number;
  width: number;
  height: number;
  scene?: StoryScene;
  characters?: CartoonCharacter[];
  audioEnvelope?: number[];
  dialogueStartSeconds?: number;
};

const clamp = (value: number, min = 0, max = 1) => Math.min(max, Math.max(min, value));

const environments: Record<string, {sky: string; glow: string; ground: string; accent: string; night?: boolean}> = {
  forest: {sky: "#7FC7D7", glow: "#E6F5D6", ground: "#3C855C", accent: "#20543F"},
  city: {sky: "#7696BD", glow: "#F0D6C1", ground: "#596C83", accent: "#283B52"},
  beach: {sky: "#6FC5E8", glow: "#FFE8B2", ground: "#E8BD78", accent: "#2789A1"},
  space: {sky: "#111A43", glow: "#3A3C78", ground: "#282B63", accent: "#9C82D7", night: true},
  castle: {sky: "#9E92C8", glow: "#F3D8E5", ground: "#82709F", accent: "#51456D"},
  school: {sky: "#8CC4E6", glow: "#F5E8C7", ground: "#9E895E", accent: "#526D8B"},
  home: {sky: "#D9A88D", glow: "#F9E6C9", ground: "#9B6C55", accent: "#644638"},
  mountain: {sky: "#7FB6DB", glow: "#E8F3FC", ground: "#648A75", accent: "#345B50"},
  desert: {sky: "#EBAE70", glow: "#FFE4B0", ground: "#C68A4D", accent: "#895B38"},
  garden: {sky: "#9ED5AE", glow: "#F0F5CE", ground: "#5F9D55", accent: "#397346"},
};

const CharacterRig: React.FC<{
  character: CartoonCharacter;
  t: number;
  mouth: number;
  motion: string;
  expression: string;
  scale: number;
  x: number;
  y: number;
  index: number;
}> = ({character, t, mouth, motion, expression, scale, x, y, index}) => {
  const appearance = character.appearance || {};
  const skin = appearance.skin_color || "#E9B58F";
  const hair = appearance.hair_color || "#3D2A25";
  const shirt = appearance.shirt_color || "#E87552";
  const pants = appearance.pants_color || "#405D86";
  const shoe = appearance.shoe_color || "#3A3441";
  const species = String(character.species || "human").toLowerCase();
  const blinkAt = [3.2, 6.8, 10.4, 14.1, 18.2, 22.5, 26.4];
  const blink = Math.max(0, ...blinkAt.map((at) => clamp(1 - Math.abs(t - at) / 0.1)));
  const eyeScale = Math.max(0.08, 1 - blink);
  const armWave = motion === "wave" ? Math.sin(t * 11 + index) * 23 : motion === "run" ? Math.sin(t * 13 + index) * 18 : motion === "walk" ? Math.sin(t * 5 + index) * 10 : 0;
  const bounce = motion === "jump" ? Math.abs(Math.sin(t * 3.3)) * 28 : motion === "run" ? Math.abs(Math.sin(t * 8)) * 9 : Math.sin(t * 2.6 + index) * 3;
  const scared = expression === "scared" || expression === "surprised";
  const sad = expression === "sad";
  const mouthY = scared ? 224 : 229;
  const hairStyle = String(appearance.hair_style || "short").toLowerCase();
  const hairPath = hairStyle === "long"
    ? <path d="M91 151 Q77 38 180 42 Q288 36 270 164 L260 285 L231 260 L230 130 Q180 88 126 132 L120 276 L94 288Z" fill={hair}/>
    : hairStyle === "curly"
      ? <path d="M91 151 Q72 56 126 52 Q143 18 176 43 Q212 8 240 54 Q292 58 270 158 Q236 115 180 112 Q126 115 91 151Z" fill={hair}/>
      : hairStyle === "spiky"
        ? <path d="M91 150 L101 84 L137 105 L151 38 L184 99 L221 40 L228 105 L270 75 L269 159 Q220 111 180 111 Q128 112 91 150Z" fill={hair}/>
        : <path d="M91 151 Q77 48 180 42 Q282 45 270 151 Q230 109 180 111 Q126 109 91 151Z" fill={hair}/>;
  const ears = species === "rabbit"
    ? <><ellipse cx="137" cy="69" rx="24" ry="72" transform="rotate(-12 137 69)" fill={skin}/><ellipse cx="223" cy="69" rx="24" ry="72" transform="rotate(12 223 69)" fill={skin}/><ellipse cx="138" cy="66" rx="10" ry="52" fill="#E99A9A"/><ellipse cx="222" cy="66" rx="10" ry="52" fill="#E99A9A"/></>
    : ["cat", "fox"].includes(species)
      ? <><path d="M102 128 L105 31 L164 104Z M258 128 L255 31 L196 104Z" fill={skin} stroke="#6D493E" strokeWidth="4"/><path d="M116 100 L119 54 L148 103Z M244 100 L241 54 L212 103Z" fill="#E99A9A"/></>
      : species === "bear"
        ? <><circle cx="112" cy="82" r="37" fill={skin}/><circle cx="248" cy="82" r="37" fill={skin}/><circle cx="112" cy="82" r="18" fill="#D99B83"/><circle cx="248" cy="82" r="18" fill="#D99B83"/></>
        : species === "dog"
          ? <><path d="M105 111 Q52 67 63 153 Q70 202 119 185 Q137 151 127 119Z" fill={hair}/><path d="M255 111 Q308 67 297 153 Q290 202 241 185 Q223 151 233 119Z" fill={hair}/></>
          : null;
  const muzzle = ["dog", "bear", "cat", "rabbit", "fox"].includes(species)
    ? <ellipse cx="180" cy="207" rx="43" ry="25" fill="#F4E5D1"/>
    : null;
  const nose = species === "owl"
    ? <path d="M165 191 L195 191 L180 219Z" fill="#E9A44A"/>
    : <ellipse cx="180" cy="198" rx="10" ry="7" fill="#30272A"/>;
  const tail = ["fox", "cat", "dog", "rabbit", "bear"].includes(species)
    ? <path d="M240 355 Q318 305 326 382 Q330 424 267 413" stroke={skin} strokeWidth="25" fill="none" strokeLinecap="round"/>
    : null;
  const mouthShape = mouth > 0.12
    ? <ellipse cx="180" cy={mouthY} rx={scared ? 12 : 15} ry={2 + mouth * 16} fill="#652D36"/>
    : sad
      ? <path d="M151 233 Q180 204 209 233" stroke="#652D36" strokeWidth="8" fill="none" strokeLinecap="round"/>
      : <path d="M148 220 Q180 248 212 220" stroke="#652D36" strokeWidth="8" fill="none" strokeLinecap="round"/>;
  return (
    <g transform={`translate(${x} ${y - 480 * scale - bounce}) scale(${scale})`}>
      <ellipse cx="180" cy="493" rx="104" ry="18" fill="#10202B" opacity=".24"/>
      {tail}
      <path d="M145 354 Q142 412 132 452" stroke={pants} strokeWidth="37" fill="none" strokeLinecap="round"/>
      <path d="M214 354 Q218 412 230 452" stroke={pants} strokeWidth="37" fill="none" strokeLinecap="round"/>
      <path d="M130 452 Q110 464 112 480 L163 480 Q174 465 151 452Z" fill={shoe}/>
      <path d="M226 452 Q210 464 220 480 L271 480 Q279 465 248 452Z" fill={shoe}/>
      <path d="M125 244 Q180 222 235 244 L251 354 Q180 385 109 354Z" fill={shirt} stroke="#FFFFFF" strokeOpacity=".2" strokeWidth="5"/>
      <g transform={`rotate(${-armWave} 123 264)`}>
        <path d="M123 264 Q82 293 76 354" stroke={skin} strokeWidth="28" fill="none" strokeLinecap="round"/>
        <circle cx="76" cy="355" r="17" fill={skin}/>
      </g>
      <g transform={`rotate(${armWave} 238 264)`}>
        <path d="M238 264 Q279 291 285 348" stroke={skin} strokeWidth="28" fill="none" strokeLinecap="round"/>
        <circle cx="285" cy="349" r="17" fill={skin}/>
      </g>
      <g>
        {ears}
        <ellipse cx="180" cy="153" rx="91" ry="106" fill={skin} stroke="#6D493E" strokeOpacity=".22" strokeWidth="5"/>
        {hairPath}
        {muzzle}
        <g transform={`translate(0 0) scale(1 ${eyeScale})`}>
          <ellipse cx="148" cy="178" rx="18" ry="22" fill="#FFFFFF"/>
          <ellipse cx="211" cy="178" rx="18" ry="22" fill="#FFFFFF"/>
          <circle cx="151" cy="181" r="10" fill="#24242B"/>
          <circle cx="214" cy="181" r="10" fill="#24242B"/>
          <circle cx="154" cy="177" r="4" fill="#FFFFFF"/>
          <circle cx="217" cy="177" r="4" fill="#FFFFFF"/>
        </g>
        <path d="M130 155 Q147 142 163 153 M198 153 Q215 142 231 155" stroke="#4A3029" strokeWidth="7" fill="none" strokeLinecap="round"/>
        {nose}
        {mouthShape}
        <ellipse cx="116" cy="205" rx="13" ry="7" fill="#E88786" opacity=".35"/>
        <ellipse cx="244" cy="205" rx="13" ry="7" fill="#E88786" opacity=".35"/>
      </g>
    </g>
  );
};

export const ClipKaroScene: React.FC<CartoonSceneProps & {time: number}> = ({
  time: t,
  durationSeconds,
  width,
  height,
  scene = {},
  characters = [],
  audioEnvelope = [],
  dialogueStartSeconds = 1,
}) => {
  const environment = environments[String(scene.environment || "forest").toLowerCase()] || environments.forest;
  const environmentName = String(scene.environment || "forest").toLowerCase();
  const motion = String(scene.motion || "idle").toLowerCase();
  const expression = String(scene.expression || "happy").toLowerCase();
  const cameraMove = String(scene.camera_move || "push-in").toLowerCase();
  const progress = clamp(t / Math.max(1 / 30, durationSeconds - 1 / 30));
  const zoom = cameraMove === "push-in"
    ? 1 + 0.09 * progress
    : cameraMove === "zoom-out"
      ? 1.12 - 0.12 * progress
      : cameraMove === "pan-left" || cameraMove === "pan-right" ? 1.035 : 1;
  const panX = cameraMove === "pan-left"
    ? width * 0.035 * (1 - 2 * progress)
    : cameraMove === "pan-right"
      ? width * 0.035 * (2 * progress - 1)
      : 0;
  const dialogueTime = t - dialogueStartSeconds;
  const envelopeIndex = Math.max(0, dialogueTime * 60);
  const lower = Math.floor(envelopeIndex);
  const upper = Math.ceil(envelopeIndex);
  const blend = envelopeIndex - lower;
  const mouth = dialogueTime >= 0
    ? clamp((audioEnvelope[lower] || 0) * (1 - blend) + (audioEnvelope[upper] || 0) * blend)
    : 0;
  const safeCharacters = characters.length ? characters.slice(0, 3) : [{id: "hero", name: "Hero"}];
  const characterHeight = height * (height > width ? 0.40 : 0.44);
  const characterScale = (characterHeight / 520) * (safeCharacters.length > 2 ? 0.82 : safeCharacters.length === 2 ? 0.92 : 1);
  const baseline = height * (height > width ? 0.62 : 0.66);
  const positions = safeCharacters.length === 1 ? [0.5] : safeCharacters.length === 2 ? [0.34, 0.66] : [0.2, 0.5, 0.8];
  const skyId = "clipkaro-scene-sky";
  const glowId = "clipkaro-scene-glow";

  return (
    <div style={{position: "absolute", inset: 0, backgroundColor: environment.sky}}>
      <svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id={skyId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={environment.sky}/>
            <stop offset="1" stopColor={environment.glow}/>
          </linearGradient>
          <radialGradient id={glowId}>
            <stop offset="0" stopColor="#FFFFFF" stopOpacity=".12"/>
            <stop offset="1" stopColor="#081525" stopOpacity=".18"/>
          </radialGradient>
        </defs>
        <g transform={`translate(${width / 2 + panX} ${height / 2}) scale(${zoom}) translate(${-width / 2} ${-height / 2})`}>
          <rect width={width} height={height} fill={`url(#${skyId})`}/>
          {environment.night
            ? <><circle cx={width * .78} cy={height * .18} r={width * .07} fill="#F3E7B8"/><circle cx={width * .81} cy={height * .16} r={width * .065} fill={environment.sky}/>{Array.from({length: 24}, (_, i) => <circle key={i} cx={(i * 137) % width} cy={(i * 79) % (height * .62)} r={2 + (i % 3)} fill="#FFFFFF" opacity=".72"/>)}</>
            : <><circle cx={width * .82} cy={height * .17} r={width * .055} fill="#FFF2B0"/><g fill="#FFFFFF" opacity=".66"><ellipse cx={width * .22} cy={height * .2} rx={width * .08} ry={height * .025}/><ellipse cx={width * .27} cy={height * .18} rx={width * .05} ry={height * .035}/><ellipse cx={width * .66} cy={height * .29} rx={width * .09} ry={height * .025}/></g></>}
          <path d={`M0 ${baseline} Q${width * .2} ${height * .55} ${width * .42} ${baseline + height * .02} T${width} ${baseline + height * .01} V${height} H0Z`} fill={environment.ground} opacity=".7"/>
          <path d={`M0 ${height * .87} Q${width * .32} ${height * .76} ${width * .58} ${height * .89} T${width} ${height * .85} V${height} H0Z`} fill={environment.accent}/>
          {String(scene.environment || "") === "forest" || String(scene.environment || "") === "garden"
            ? <g fill="#2F7652"><circle cx={width * .12} cy={height * .53} r={width * .09}/><circle cx={width * .87} cy={height * .5} r={width * .1}/><rect x={width * .1} y={height * .52} width={width * .04} height={height * .28} fill="#70503A"/><rect x={width * .85} y={height * .5} width={width * .04} height={height * .3} fill="#70503A"/></g>
            : String(scene.environment || "") === "city"
              ? <g fill={environment.accent}>{[.04, .2, .4, .63, .82].map((x, i) => <rect key={i} x={width * x} y={height * (.55 - (i % 2) * .1)} width={width * .12} height={height * (.28 + (i % 2) * .1)} rx="8"/>)}</g>
              : <path d={`M0 ${height * .76} L${width * .2} ${height * .45} L${width * .38} ${height * .76} L${width * .62} ${height * .42} L${width * .86} ${height * .76}Z`} fill={environment.accent} opacity=".5"/>}
          {environmentName === "home" ? (
            <g>
              <rect width={width} height={height} fill="#8D6E65"/>
              <rect y={baseline} width={width} height={height - baseline} fill="#40333A"/>
              <path d={"M0 " + baseline + " Q" + width * .5 + " " + (baseline - height * .02) + " " + width + " " + baseline} stroke="#C39B83" strokeWidth="8" fill="none" opacity=".65"/>
              <rect x={width * .065} y={height * .12} width={width * .31} height={height * .39} rx="10" fill="#20354A" stroke="#D8C0A5" strokeWidth="16"/>
              <rect x={width * .085} y={height * .14} width={width * .27} height={height * .35} fill="#304F69"/>
              <circle cx={width * .29} cy={height * .22} r={width * .035} fill="#E8E0C6"/>
              <circle cx={width * .305} cy={height * .205} r={width * .033} fill="#304F69"/>
              <path d={"M" + width * .085 + " " + height * .42 + " L" + width * .17 + " " + height * .33 + " L" + width * .23 + " " + height * .39 + " L" + width * .355 + " " + height * .31 + " V" + height * .49 + " H" + width * .085 + "Z"} fill="#172A3B"/>
              <path d={"M" + width * .045 + " " + height * .1 + " Q" + width * .1 + " " + height * .2 + " " + width * .07 + " " + height * .54 + " L" + width * .12 + " " + height * .54 + " Q" + width * .15 + " " + height * .25 + " " + width * .13 + " " + height * .1 + "Z"} fill="#554554"/>
              <path d={"M" + width * .32 + " " + height * .1 + " Q" + width * .29 + " " + height * .27 + " " + width * .35 + " " + height * .54 + " L" + width * .39 + " " + height * .54 + " Q" + width * .35 + " " + height * .22 + " " + width * .39 + " " + height * .1 + "Z"} fill="#554554"/>
              <rect x={width * .76} y={height * .11} width={width * .19} height={height * .55} rx="8" fill="#4A302D" stroke="#C6A88A" strokeWidth="12"/>
              <rect x={width * .78} y={height * .14} width={width * .15} height={height * .49} fill="#68453B"/>
              <circle cx={width * .91} cy={height * .46} r="9" fill="#D7B985"/>
              <rect x={width * .46} y={height * .17} width={width * .2} height={height * .13} rx="5" fill="#463C45" stroke="#D5BDA2" strokeWidth="9"/>
              <path d={"M" + width * .48 + " " + height * .28 + " L" + width * .54 + " " + height * .2 + " L" + width * .61 + " " + height * .28 + "Z"} fill="#8A9B9B"/>
              <rect x={width * .26} y={height * .74} width={width * .67} height={height * .15} rx="18" fill="#4B353A" stroke="#2C2831" strokeWidth="10"/>
              <rect x={width * .28} y={height * .69} width={width * .63} height={height * .11} rx="30" fill="#B9C6C8" stroke="#586B73" strokeWidth="8"/>
              <path d={"M" + width * .28 + " " + height * .77 + " Q" + width * .58 + " " + height * .73 + " " + width * .93 + " " + height * .78 + " V" + height * .88 + " Q" + width * .58 + " " + height * .92 + " " + width * .28 + " " + height * .87 + "Z"} fill="#75677E" stroke="#3F3748" strokeWidth="6"/>
              <path d={"M" + width * .31 + " " + height * .8 + " Q" + width * .6 + " " + height * .77 + " " + width * .9 + " " + height * .81} stroke="#C7B9C8" strokeWidth="5" opacity=".5" fill="none"/>
              <rect x={width * .06} y={height * .7} width={width * .16} height={height * .13} rx="8" fill="#523C3A"/>
              <rect x={width * .075} y={height * .72} width={width * .13} height={height * .045} fill="#8C756D"/>
              <path d={"M" + width * .14 + " " + height * .7 + " V" + height * .59 + " M" + width * .1 + " " + height * .59 + " H" + width * .18 + " L" + width * .2 + " " + height * .68 + " H" + width * .08 + "Z"} fill="#D6B48A" stroke="#6B514A" strokeWidth="5"/>
              <ellipse cx={width * .14} cy={height * .58} rx={width * .055} ry={height * .035} fill="#E8C99C"/>
              <ellipse cx={width * .5} cy={height * .86} rx={width * .3} ry={height * .025} fill="#211E26" opacity=".28"/>
            </g>
          ) : null}
          {safeCharacters.map((character, index) => {
            const center = width * positions[index];
            const x = center - 180 * characterScale;
            const speaker = String(character.id) === String(scene.speaker_id || safeCharacters[0].id);
            return (
              <CharacterRig
                key={character.id || index}
                character={character}
                t={t}
                mouth={speaker ? mouth : 0}
                motion={motion}
                expression={expression}
                scale={characterScale}
                x={x}
                y={baseline}
                index={index}
              />
            );
          })}
          <rect width={width} height={height} fill={`url(#${glowId})`}/>
        </g>
      </svg>
    </div>
  );
};
