import fs from "node:fs";
import path from "node:path";

const root = path.resolve(process.cwd(), "..");
const read = (relative) => fs.readFileSync(path.join(root, relative), "utf8");
const requireText = (text, needle, label) => {
  if (!text.includes(needle)) throw new Error(`Landscape reframe contract failed: ${label}`);
};

const editor = read("frontend/app/editor/[clipId]/page.tsx");
const css = read("frontend/app/globals.css");
const schema = read("backend/app/schemas/api.py");
const rendering = read("backend/app/services/rendering.py");
const indiaQuality = read("backend/app/services/india_quality.py");
const cropTracking = read("backend/app/services/crop_tracking.py");

// The product fallback is only truthful if creators can actually adjust one
// horizontal focus value and see the same crop semantics before exporting.
requireText(editor, "const [focusX, setFocusX] = useState(50);", "manual focus state must exist");
requireText(editor, "Manual reframe: {focusX}%", "manual focus must remain visible in Creator Studio");
requireText(editor, 'className="focus-slider" type="range" min="0" max="100"', "manual focus must expose the full 0..100 range");
requireText(editor, 'objectPosition: String(focusX) + "% 50%"', "preview must react to the exact manual focus value");
requireText(editor, 'objectFit: preserveSourceCaptions ? "contain" : "cover"', "preview must expose source-caption safe framing");
requireText(editor, "focus_x: focusX", "export request must send the previewed manual focus value");
requireText(editor, "preserve_source_captions: preserveSourceCaptions", "export request must send source-caption safe framing choice");
requireText(editor, "India Quality Mode", "creator studio must expose the India Quality Mode control");
requireText(editor, "caption_language_style: captionLanguageStyle", "export request must send the caption language style");
requireText(editor, "reviewSuggested &&", "creator studio must gate transcript review warnings from backend truth");
requireText(editor, "<b>Review suggested</b>", "creator studio must surface transcript review warnings");
requireText(editor, 'Frame <b>{preserveSourceCaptions ? "Full" : Math.round(focusX) + "%"}</b>', "export summary must disclose crop versus full-frame mode");
requireText(css, ".video-canvas video{width:100%;height:100%;object-fit:cover}", "preview must use cover-crop semantics like FFmpeg");

// The backend must validate and consume the same value. Keep dynamic keyframe
// support intact even while automatic discovery/tracking remains a separate QA decision.
requireText(schema, "focus_x: float = Field(default=50, ge=0, le=100)", "backend must bound focus_x to 0..100");
requireText(schema, "crop_keyframes: list[CropKeyframe]", "backend must retain time-varying focus support");
requireText(schema, "preserve_source_captions: bool = False", "backend must accept explicit source-caption preservation");
requireText(schema, "india_quality_mode: bool = False", "backend must default India Quality Mode off");
requireText(schema, 'caption_language_style: str = Field(default="auto"', "backend must accept caption language style without breaking old clients");
requireText(indiaQuality, "def caption_segments_for_export", "India caption preparation must stay in a testable backend service");
requireText(indiaQuality, "def effective_caption_position", "India source-caption safe placement must be explicit");
requireText(rendering, "force_original_aspect_ratio=decrease", "renderer must preserve the full source frame for source-caption safe exports");
requireText(rendering, "pad={width}:{height}:(ow-iw)/2:(oh-ih)/2", "renderer must pad preserved source-caption exports instead of cropping text away");
requireText(rendering, 'f"scale={width}:{height}:force_original_aspect_ratio=increase"', "renderer must fill the target before cropping");
requireText(rendering, 'f"crop={width}:{height}:(iw-{width})*{focus_expression}:(ih-{height})/2"', "renderer must use horizontal focus for the production crop");
requireText(cropTracking, "18.0 * elapsed", "dynamic crop smoothing limit must remain explicit and reviewable");

console.log("Landscape reframe contract: passed");
