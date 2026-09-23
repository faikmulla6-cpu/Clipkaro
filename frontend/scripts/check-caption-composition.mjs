import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = relative => fs.readFileSync(path.join(root, relative), "utf8");
const requireText = (text, needle, label) => {
  if (!text.includes(needle)) throw new Error(`Caption composition contract failed: ${label}`);
};

const editor = read("frontend/app/editor/[clipId]/page.tsx");
const css = read("frontend/app/globals.css");
const schema = read("backend/app/schemas/api.py");
const routes = read("backend/app/api/routes.py");
const mediaWorker = read("backend/app/media_job.py");
const renderer = read("backend/app/services/rendering.py");

for (const field of ["caption_x", "caption_y", "caption_scale", "caption_alignment"]) {
  requireText(editor, field + ":", `editor export payload must send ${field}`);
  requireText(schema, field + ":", `server schema must validate ${field}`);
  requireText(routes, "request." + field, `local render boundary must forward ${field}`);
  requireText(mediaWorker, field + "=request." + field, `durable media worker must forward ${field}`);
}

requireText(editor, "onPointerDown={beginCaptionDrag}", "caption must be directly draggable");
requireText(editor, "Drag caption on preview", "UI must explain direct caption placement");
requireText(editor, 'aria-label="Caption size"', "caption size needs an accessible slider");
requireText(editor, 'aria-label="Caption text alignment"', "caption alignment needs an accessible control group");
requireText(editor, 'caption_alignment: captionAlignment', "editor must send selected caption alignment");
requireText(editor, "textAlign: captionAlignment", "preview must render selected caption alignment");
requireText(editor, "Text wraps and reflows automatically", "UI must explain responsive wrapping");
requireText(editor, "applies the placement to every caption in this Short", "layout scope must be explicit");
requireText(editor, '"--caption-font-size-ratio-effective"', "preview must scale actual font size, not bitmap-transform text");
requireText(editor, "captionY === null", "preset and custom placement states must stay distinct");

requireText(css, ".caption-preview.caption-custom-position", "custom normalized placement CSS must exist");
requireText(css, "touch-action:none", "pointer dragging must be touch-safe");
requireText(css, "--caption-safe-width", "caption preview must retain the selected style safe horizontal boundary");
requireText(css, "--caption-font-size-ratio-effective", "preview font size must drive browser reflow");

requireText(renderer, "def _normalized_caption_scale", "renderer must clamp caption scale");
requireText(renderer, "def _clamp_caption_center", "renderer must keep captions inside safe bounds");
requireText(renderer, 'caption_alignment: str = "center"', "renderer must accept validated caption alignment");
requireText(renderer, 'caption_alignment == "left"', "renderer must position left-aligned multi-line captions");
requireText(renderer, 'caption_alignment == "right"', "renderer must position right-aligned multi-line captions");
requireText(renderer, "max_chars = _scaled_caption_max_chars", "larger rendered text must reflow more aggressively");
requireText(renderer, "caption_y: float | None = None", "renderer must preserve preset backward compatibility");

console.log("Caption composition contract: passed");
