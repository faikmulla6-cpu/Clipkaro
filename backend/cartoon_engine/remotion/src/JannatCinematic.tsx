import React from "react";
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from "remotion";
import {renderFilm} from "./templates/jannat/film";

export type JannatCinematicProps = {
  durationSeconds: number;
  episodeLipEnvelope: number[];
};

export const JannatCinematic: React.FC<JannatCinematicProps> = ({
  durationSeconds = 30,
  episodeLipEnvelope = [],
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const seconds = frame / fps;
  const svg = renderFilm(seconds, episodeLipEnvelope, {durationSeconds});

  return (
    <AbsoluteFill style={{backgroundColor: "#0e1823"}}>
      <div
        style={{width: "100%", height: "100%"}}
        dangerouslySetInnerHTML={{__html: svg}}
      />
    </AbsoluteFill>
  );
};
