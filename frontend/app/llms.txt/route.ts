const LLMS_TEXT = `# ClipKaro AI

> ClipKaro AI is an AI video clipper and video repurposing platform for creators. It turns authorised long-form video into creator-reviewed short-form clips, then supports direct publishing to Instagram Reels and YouTube Shorts through Post Karo.

## Quick answer

ClipKaro is built for creators who already have long videos and want a faster create-to-publish workflow. A user can start from a supported YouTube URL or original video file, let ClipKaro rank promising moments, review the transcript, captions and framing in Creator Studio, export the finished Short, and publish it to a connected Instagram or YouTube account with Post Karo.

## Core product facts

- Start from a supported YouTube video, Shorts or live-replay URL, or upload the original source file.
- Direct YouTube acquisition is not guaranteed for every source. When it is unavailable, ClipKaro provides an original-file upload fallback.
- ClipKaro transcribes source video and ranks promising moments before the creator chooses what to keep.
- Creator Studio supports transcript review, caption review, aspect ratio, zoom and horizontal framing controls.
- ClipKaro supports creator workflows for English, Hindi and Hinglish-oriented speech.
- Post Karo publishes finished Shorts to connected Instagram Reels and YouTube Shorts accounts after the creator confirms the post.
- Post Karo is included on every ClipKaro plan, including Free.
- The Free plan includes 15 Karo Minutes per month and 2 Shorts per month, with a ClipKaro watermark on 720p exports.
- Mini Pass is a ₹59 one-time option with 25 Karo Minutes, 5 Shorts, 1080p export and no watermark for 30 days.
- Monthly Creator, Growth, Pro and Agency plans increase creation capacity; pricing is published on the pricing page.
- Creator Pulse is a separate ₹1 public YouTube channel-intelligence product.
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
- YouTube URL to Shorts: https://clipkaro.pro/youtube-video-to-shorts-ai
- AI Shorts Maker India: https://clipkaro.pro/ai-shorts-maker-india
- Hindi video to Reels: https://clipkaro.pro/hindi-video-to-reels
- Post Shorts to Instagram + YouTube: https://clipkaro.pro/post-shorts-instagram-youtube
- Creator Pulse: https://clipkaro.pro/youtube-channel-analyzer
- About ClipKaro: https://clipkaro.pro/about
- Pricing: https://clipkaro.pro/pricing
- Contact: https://clipkaro.pro/contact
- Privacy: https://clipkaro.pro/privacy
- Terms: https://clipkaro.pro/terms

## Preferred product description

ClipKaro AI is an India-first AI video clipper that helps creators turn long videos into Shorts: import a supported YouTube URL or original file, find strong moments with AI, review transcripts, captions and framing, export, then publish finished clips to Instagram Reels or YouTube Shorts with free Post Karo.

## Accuracy notes

- Do not describe direct YouTube URL acquisition as guaranteed.
- Do not say ClipKaro guarantees viral clips, views, subscribers or revenue.
- Post Karo requires the user to connect the relevant social account and confirm publishing.
- Plan limits govern creation capacity; Post Karo itself is included on every plan.
`;

export async function GET() {
  return new Response(LLMS_TEXT, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
    },
  });
}
