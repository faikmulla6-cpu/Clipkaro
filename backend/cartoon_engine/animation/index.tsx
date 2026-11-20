import React from "react";
import {flushSync} from "react-dom";
import {createRoot} from "react-dom/client";
import {ClipKaroScene, type CartoonSceneProps} from "./CartoonScene";
import {renderFilm} from "./jannat.js";

type Animation = (
  | {kind: "jannat"; envelope: number[]}
  | {kind: "cartoon"; scenes: (CartoonSceneProps & {start: number})[]}
) & {duration: number};

export function createFrameRenderer(element: HTMLElement, animation: Animation) {
  if (animation.kind === "jannat") {
    return (time: number) => {
      element.innerHTML = renderFilm(time, animation.envelope, {durationSeconds: animation.duration});
    };
  }

  const root = createRoot(element);
  return (time: number) => {
    const scene = animation.scenes.findLast((item) => item.start <= time) ?? animation.scenes[0];
    flushSync(() => root.render(<ClipKaroScene {...scene} time={Math.max(0, time - scene.start)} />));
  };
}
