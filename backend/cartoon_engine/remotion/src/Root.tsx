import React from "react";
import {Composition} from "remotion";
import {ClipKaroScene, type CartoonSceneProps} from "./CartoonScene";
import {JannatCinematic, type JannatCinematicProps} from "./JannatCinematic";

const sceneDefaults: CartoonSceneProps = {
  durationSeconds: 5,
  aspectRatio: "9:16",
  scene: {
    id: "scene-demo",
    scene_title: "A new beginning",
    environment: "home",
    expression: "curious",
    motion: "look",
    camera_move: "push-in",
    speaker_id: "jannat",
    action: "A character wakes up and looks around",
  },
  characters: [{
    id: "jannat",
    name: "Jannat",
    species: "human",
    appearance: {
      skin_color: "#ca9a85",
      hair_color: "#121c29",
      shirt_color: "#306b73",
      pants_color: "#306b73",
      shoe_color: "#17202b",
      hair_style: "long",
    },
  }],
  audioEnvelope: [],
  dialogueStartSeconds: 1,
};

const jannatDefaults: JannatCinematicProps = {
  durationSeconds: 30,
  episodeLipEnvelope: [],
};

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="ClipKaroScene"
      component={ClipKaroScene}
      durationInFrames={150}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={sceneDefaults}
      calculateMetadata={({props}) => {
        const durationSeconds = Math.max(1, Math.min(60, Number(props.durationSeconds || 5)));
        const dimensions = props.aspectRatio === "16:9"
          ? {width: 1920, height: 1080}
          : props.aspectRatio === "1:1"
            ? {width: 1080, height: 1080}
            : {width: 1080, height: 1920};
        return {durationInFrames: Math.round(durationSeconds * 30), ...dimensions};
      }}
    />
    <Composition
      id="ClipKaroJannatCinematic"
      component={JannatCinematic}
      durationInFrames={900}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={jannatDefaults}
      calculateMetadata={({props}) => {
        const durationSeconds = Math.max(1, Math.min(60, Number(props.durationSeconds || 30)));
        return {durationInFrames: Math.round(durationSeconds * 30), width: 1920, height: 1080};
      }}
    />
  </>
);
