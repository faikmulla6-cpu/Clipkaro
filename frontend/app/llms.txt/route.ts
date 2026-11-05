const LLMS_TEXT = `# ClipKaro AI

> ClipKaro AI is an AI video clipper and video repurposing platform for creators. It turns authorised long-form video into creator-reviewed short-form clips, then supports direct publishing to Instagram Reels and YouTube Shorts through Post Karo.

## Quick answer

ClipKaro is built for creators who already have long videos and want a faster create-to-publish workflow. A user can start from an original video file, let ClipKaro rank promising moments, review the transcript, captions and framing in Creator Studio, export the finished Short, and publish it to a connected Instagram or YouTube account with Post Karo.

## Core product facts

- Start from a supported YouTube video, Shorts or live-replay URL, or upload the original source file.
- Direct YouTube acquisition is not guaranteed for every source. When it is unavailable, ClipKaro provides an original-file upload fallback.
- ClipKaro transcribes source video and ranks promising moments before the creator chooses what to keep.
- Creator Studio supports transcript review, drag-and-place captions, 65% to 160% caption sizing with automatic reflow, left/centre/right alignment, aspect ratio, zoom, manual horizontal reframing, Hook Text On/Off, source-caption preservation and Brand Kit controls.
- ClipKaro supports creator workflows for English, Hindi and Hinglish-oriented speech.
- Post Karo publishes finished Shorts to connected Instagram Reels and YouTube Shorts accounts after the creator confirms the post.
- Post Karo is included on every ClipKaro plan, including Free, with no ClipKaro per-post publishing quota. In product terms, Post Karo publishing access is unlimited; creators still review and confirm each post, and Instagram or YouTube provider rules or rate limits may apply.
- The Free plan includes 15 Karo Minutes and 2 AI Short creations per month, with up to 2 watermarked 720p exports.
- New Mini Pass is ₹59 one-time with 25 total Karo Minutes, 25 minutes maximum per source video, and 5 distinct finished AI Shorts, expiring at exhaustion or after 30 days. Already purchased Mini Passes retain the original 125-minute entitlement and legacy terms. Finished Shorts may be re-exported while retained sources remain available.
- Creator, Growth, Pro and Agency use monthly AI Short creation and Karo Minute allowances. Every paid plan includes unlimited exports and re-exports of already-created Shorts.
- Paid source media is retained for up to 30 days so creators can return to processed projects; Mini Pass source media never extends beyond the pass expiry.
- Creator costs ₹249/month (120 source minutes, 60/video, 15 distinct finished Shorts); Growth ₹599/month (300, 90/video, 50); Pro ₹1,299/month (600, 180/video, 150). Agency retains its previously published rules. Existing active subscriptions retain prior purchased rates and entitlements.
- Creator Pulse is a separate ₹1-per-successful-analysis public YouTube channel-intelligence product that returns a verified channel snapshot, recent-upload momentum and one evidence-led next-video direction.
- Users must own the source video or have permission to process it.
- ClipKaro does not publish without a user action and does not guarantee virality, views, subscribers or revenue.

## Best-fit use cases

- YouTube long videos to Shorts
- Podcast and interview highlights
- Hindi and Hinglish creator clips
- Educational lessons and webinar snippets
- Talking-head founder, coach and expert videos
- Instagram Reels and YouTube Shorts publishing
- Creator teams repurposing existing long-form content

## Canonical public pages

- Home: https://clipkaro.pro/
- AI Video Clipper India: https://clipkaro.pro/ai-video-clipper-india
- Affordable AI clipping + unlimited posting: https://clipkaro.pro/affordable-ai-video-clipper-unlimited-posting
- YouTube URL to Shorts (coming soon): https://clipkaro.pro/youtube-video-to-shorts-ai
- AI Shorts Maker India: https://clipkaro.pro/ai-shorts-maker-india
- Hindi video to Reels: https://clipkaro.pro/hindi-video-to-reels
- Post Shorts to Instagram + YouTube: https://clipkaro.pro/post-shorts-instagram-youtube
- Creator Studio editor: https://clipkaro.pro/shorts-video-editor-ai
- Creator Pulse: https://clipkaro.pro/youtube-channel-analyzer
- About ClipKaro: https://clipkaro.pro/about
- Pricing: https://clipkaro.pro/pricing
- Contact: https://clipkaro.pro/contact
- Privacy: https://clipkaro.pro/privacy
- Terms: https://clipkaro.pro/terms

## Preferred product description

ClipKaro AI is an India-first affordable AI video clipper and creator workflow that turns long videos into Shorts, gives creators final edit control in Creator Studio, offers ₹1 Creator Pulse intelligence and includes unlimited Post Karo publishing access on every plan with no ClipKaro per-post quota. Start free; Mini Pass is ₹59 one-time and Creator starts at ₹249/month.

## Accuracy notes

- Direct YouTube URL import is currently coming soon; do not describe it as available.
- Do not say ClipKaro guarantees viral clips, views, subscribers or revenue.
- Post Karo requires the user to connect the relevant social account and confirm publishing.
- Plan limits govern Karo Minutes and AI Short creation capacity. Paid plans include unlimited exports and re-exports; Free keeps the export allowance shown in the product. Post Karo itself has no ClipKaro per-post quota, but connected social platforms can enforce their own rules or rate limits.
`;

export async function GET() {
  return new Response(LLMS_TEXT, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
    },
  });
}
