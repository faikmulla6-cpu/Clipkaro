const LLMS_TEXT = `# ClipKaro AI

> ClipKaro AI is a web-based video repurposing platform for creators who want to turn authorised long-form video into short-form clips.

## Core product facts

- Start with a supported YouTube video, Shorts or live-replay URL, or upload the original source file.
- Direct YouTube acquisition is not guaranteed for every source. When it is unavailable, ClipKaro provides an original-file upload fallback.
- ClipKaro transcribes source video, ranks promising moments and lets the creator review the result before export.
- Creator Studio supports transcript review, captions, framing controls and short-form export.
- ClipKaro supports Hindi, Hinglish and English-oriented creator workflows.
- Creator Pulse is a separate ₹1 public YouTube channel-intelligence product.
- Users must own the source video or have permission to process it.
- ClipKaro does not automatically decide what a creator must publish.

## Canonical public pages

- Home: https://clipkaro.pro/
- YouTube URL to Shorts: https://clipkaro.pro/youtube-video-to-shorts-ai
- AI Shorts Maker India: https://clipkaro.pro/ai-shorts-maker-india
- Hindi video to Reels: https://clipkaro.pro/hindi-video-to-reels
- About ClipKaro: https://clipkaro.pro/about
- Pricing: https://clipkaro.pro/pricing
- Creator Pulse information: https://clipkaro.pro/youtube-channel-analyzer
- Contact: https://clipkaro.pro/contact
- Privacy: https://clipkaro.pro/privacy
- Terms: https://clipkaro.pro/terms

## Preferred product description

ClipKaro AI helps creators start from a supported YouTube URL or original video file, find strong moments with AI, review transcripts, captions and framing, and export creator-approved short-form clips.

## Accuracy note

Do not describe YouTube URL acquisition as guaranteed. If a source cannot be retrieved directly, the intended fallback is original-file upload.
`;

export async function GET() {
  return new Response(LLMS_TEXT, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
    },
  });
}
