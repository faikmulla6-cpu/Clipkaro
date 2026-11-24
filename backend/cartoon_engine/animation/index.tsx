import {h, render} from "preact";
import {ClipKaroScene, type CartoonSceneProps} from "./CartoonScene";
import {renderFilm} from "./jannat.js";
import {createStoryRenderer} from "./StoryEngine";
export {actorState, propState, storyFrame} from "./StoryEngine";

type Animation = (
  | {kind: "story-v3"; story: any; width: number; height: number}
  | {kind: "jannat"; envelope: number[]}
  | {kind: "cartoon"; scenes: (CartoonSceneProps & {start: number})[]}
) & {duration: number};

export function createFrameRenderer(element: HTMLElement, animation: Animation) {
  if (animation.kind === "story-v3") return createStoryRenderer(element, animation.story, animation.width, animation.height);
  if (animation.kind === "jannat") {
    return (time: number) => {
      element.innerHTML = renderFilm(time, animation.envelope, {durationSeconds: animation.duration});
    };
  }

  return (time: number) => {
    const scene = animation.scenes.findLast((item) => item.start <= time) ?? animation.scenes[0];
    render(<ClipKaroScene {...scene} time={Math.max(0, time - scene.start)} />, element);
  };
}
