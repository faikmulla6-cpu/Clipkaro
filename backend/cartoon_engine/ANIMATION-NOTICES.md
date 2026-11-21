# Cartoon Studio V3 notices

The director executor and biped rig in animation/StoryEngine.tsx are new ClipKaro source.
Reference film techniques were studied; its Remotion source and runtime were not copied into V3.
The earlier legacy Jannat path remains for saved projects and is not the V3 implementation.

Existing runtime dependencies are unchanged:

- Preact 11.2.0: MIT; https://github.com/preactjs/preact/blob/main/LICENSE
- GSAP 3.15.0: preserve its distribution header and Standard License; https://gsap.com/community/standard-license/
- HyperFrames 0.9.72: see the installed distribution LICENSE and notices.
- esbuild 0.28.2: MIT; https://github.com/evanw/esbuild/blob/main/LICENSE.md

Editable packages retain bundled library headers. Speech recordings use the selected
provider and retain provider/word-timing provenance. Edge speech is an external
service; it is not an owned voice model. Procedural score and foley are original
ClipKaro-generated PCM stems.
