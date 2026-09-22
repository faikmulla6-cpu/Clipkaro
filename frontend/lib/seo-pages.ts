import { SEO_PAGE_SLUGS } from "@/lib/seo-page-slugs";

export type SeoPage = {
  slug: (typeof SEO_PAGE_SLUGS)[number];
  title: string;
  metaTitle: string;
  description: string;
  eyebrow: string;
  h1: string;
  lead: string;
  audience: string;
  promise: string;
  workflow: string[];
  useCases: string[];
  trust: string;
  faq: Array<{ question: string; answer: string }>;
};

export const SEO_PAGES: SeoPage[] = [
  {
    slug: SEO_PAGE_SLUGS[0],
    title: "YouTube URL to Shorts AI",
    metaTitle: "YouTube URL to Shorts AI for Indian Creators | ClipKaro AI",
    description: "Paste a supported YouTube URL or upload the original file, then turn long-form video into creator-ready Shorts with AI clip scoring, captions and editing.",
    eyebrow: "YouTube URL to Shorts",
    h1: "Turn a YouTube URL into creator-ready Shorts",
    lead: "Paste a supported YouTube video, Shorts or live-replay link, or upload the original file when direct acquisition is unavailable. ClipKaro then finds short, understandable moments with hooks, captions and vertical exports.",
    audience: "YouTubers, educators, coaches and founders who already have long videos and need more Shorts without editing every timeline manually.",
    promise: "ClipKaro gives you a fast URL-first path when the source is retrievable and a clear original-file fallback when it is not, while keeping analysis, editing and export inside one creator workflow.",
    workflow: [
      "Paste a supported YouTube URL for content you own or have permission to process, or upload the original MP4, MOV, WebM or MKV.",
      "If direct URL acquisition is unavailable, switch to original-file upload instead of restarting the workflow.",
      "Review AI-ranked moments with titles, hooks, reasons, transcript text and framing controls.",
      "Export selected clips as vertical Shorts with creator-approved captions.",
    ],
    useCases: ["YouTube long videos", "Podcast highlights", "Educational explainers", "Founder videos", "Webinar snippets", "Interview answers"],
    trust: "Direct YouTube acquisition depends on the source being retrievable. ClipKaro keeps rights confirmation explicit and provides original-file upload as the fallback when a URL cannot be acquired.",
    faq: [
      { question: "Can I paste a YouTube URL?", answer: "Yes. ClipKaro accepts supported YouTube video, Shorts and live-replay URLs for content you own or have permission to process." },
      { question: "What if the YouTube URL cannot be imported?", answer: "Use the original-file upload fallback. The video then continues through the same transcript, clip-finding, editing and export workflow." },
      { question: "Will the clips be 9:16?", answer: "Creator Studio supports vertical short-form framing and lets you review the crop, captions and final export before publishing." },
      { question: "Does it choose clips automatically?", answer: "It ranks promising moments and explains why they may work, while you keep final creative control before export." },
    ],
  },
  {
    slug: SEO_PAGE_SLUGS[1],
    title: "Hindi Video to Reels",
    metaTitle: "Hindi Video to Instagram Reels AI | ClipKaro AI",
    description: "Create captioned Instagram Reels from Hindi talking-head videos, podcasts, lessons and creator recordings with ClipKaro AI.",
    eyebrow: "Hindi creator workflow",
    h1: "Make Hindi videos easier to turn into Reels",
    lead: "ClipKaro supports Hindi workflows for creators who want short vertical clips, clear captions and fewer manual editing hours.",
    audience: "Hindi creators, educators, coaches, devotional creators and local-business owners who publish short videos for Indian audiences.",
    promise: "Upload one long Hindi video, review the AI's suggested moments, and export the best short clips for Reels or Shorts.",
    workflow: [
      "Select Hindi before processing, or use auto-detect when you are unsure.",
      "Let the transcript and clip scorer identify self-contained moments.",
      "Preview suggestions for hook quality, context and ending before export.",
      "Export vertical clips with caption styling suited to mobile viewing.",
    ],
    useCases: ["Hindi lessons", "Motivation videos", "Business advice", "Spiritual talks", "Local business explainers", "Creator Q&A"],
    trust: "Hindi and Hinglish creator workflows are supported, but mixed-language speech can still produce uncertain transcript lines. Review the transcript and captions before publishing.",
    faq: [
      { question: "Is Hindi supported?", answer: "Yes. ClipKaro includes Hindi as a supported spoken-language choice in the upload workflow." },
      { question: "Does ClipKaro support Hinglish?", answer: "Yes. ClipKaro supports Hinglish-oriented creator workflows. Because mixed-language speech can contain uncertain transcript lines, review the transcript and captions before publishing." },
      { question: "Can I use these clips for Instagram?", answer: "Yes. The vertical export workflow is designed for platforms like Instagram Reels and YouTube Shorts." },
    ],
  },
  {
    slug: SEO_PAGE_SLUGS[2],
    title: "Podcast to Clips India",
    metaTitle: "Podcast to Clips AI for India | ClipKaro AI",
    description: "Repurpose Indian podcasts, interviews and long conversations into short captioned clips for YouTube Shorts, Instagram Reels and LinkedIn.",
    eyebrow: "Podcast repurposing",
    h1: "Turn podcast episodes into short clips for Indian audiences",
    lead: "Find the strongest answers, stories and teaching moments inside long conversations without manually scrubbing the whole recording.",
    audience: "Podcast hosts, guest-led YouTube channels, interview shows, personal-brand teams and agencies serving Indian creators.",
    promise: "ClipKaro scores moments by hook, clarity, value and clean endings so your podcast becomes a repeatable short-form content engine.",
    workflow: [
      "Upload the podcast video recording after editing or exporting it from your recording tool.",
      "Select Podcast as the content type to guide clip discovery.",
      "Review suggested highlights with titles and reasons.",
      "Export clips for Shorts, Reels or client review.",
    ],
    useCases: ["Interview answers", "Founder stories", "Expert advice", "Debate moments", "Coaching calls", "Panel discussions"],
    trust: "The best podcast clips still need human judgment. ClipKaro reduces discovery and captioning time; it does not replace editorial taste.",
    faq: [
      { question: "Can ClipKaro process long podcasts?", answer: "Plan limits are based on Karo Minutes and exports, so longer episodes may require a paid plan depending on duration and usage." },
      { question: "Does it remove every pause?", answer: "ClipKaro focuses on finding and exporting strong moments. Review the editor/export result before publishing." },
      { question: "Is this for agencies too?", answer: "Yes. Podcast and personal-brand agencies can use the workflow to create repeatable highlight batches for clients." },
    ],
  },
  {
    slug: SEO_PAGE_SLUGS[3],
    title: "AI Shorts Maker India",
    metaTitle: "AI Shorts Maker for Indian Creators | ClipKaro AI",
    description: "An India-first AI Shorts maker for turning creator videos into ranked short clips with captions, hooks and vertical exports.",
    eyebrow: "India-first Shorts maker",
    h1: "AI Shorts creation built around Indian creator workflows",
    lead: "ClipKaro helps creators in India convert long videos into short, captioned, vertical clips without a complex editing timeline.",
    audience: "Indian YouTubers, Instagram creators, educators, podcasters, coaches and small teams that need more short-form output from existing videos.",
    promise: "Instead of starting with a blank editor, start with ranked clip suggestions and export the ones that fit your audience.",
    workflow: [
      "Upload your source video.",
      "Pick language and content category.",
      "Compare ranked clip suggestions.",
      "Export no-watermark Shorts on paid plans.",
    ],
    useCases: ["YouTube Shorts", "Instagram Reels", "Course clips", "Coach clips", "Business explainers", "Creator highlights"],
    trust: "ClipKaro keeps the product focused on owned or permissioned content and publishes support, privacy and grievance contact details before paid checkout.",
    faq: [
      { question: "Why use ClipKaro instead of a normal editor?", answer: "A normal editor still makes you find the moment. ClipKaro starts by ranking moments and producing creator-friendly clip metadata." },
      { question: "Is there a one-time option?", answer: "Yes. ClipKaro includes a Mini Pass for creators who want a small paid pack without starting a subscription." },
      { question: "Who is it best for?", answer: "It is best for creators with existing long videos who want to publish more Shorts and Reels consistently." },
    ],
  },
  {
    slug: SEO_PAGE_SLUGS[4],
    title: "Instagram Reels Maker AI",
    metaTitle: "Instagram Reels Maker AI from Long Videos | ClipKaro AI",
    description: "Create Instagram Reels from long videos with AI-ranked moments, vertical formatting and readable captions.",
    eyebrow: "Reels from long videos",
    h1: "Create Instagram Reels from videos you already recorded",
    lead: "Repurpose lessons, talks, podcasts and creator videos into vertical Reels without manually searching for every highlight.",
    audience: "Instagram creators, coaches, local businesses and social-media managers who already have long videos but need more short-form posts.",
    promise: "ClipKaro gives you a faster path from source video to captioned Reel-ready MP4.",
    workflow: [
      "Upload the long video you want to repurpose.",
      "Review short moments ranked for hook and clarity.",
      "Choose the clip that fits your Instagram audience.",
      "Export the vertical captioned video, then use Post Karo to publish the finished Short to a connected Instagram account or download it for another workflow.",
    ],
    useCases: ["Talking-head advice", "Tutorial moments", "Podcast snippets", "Client testimonials", "Product explainers", "Webinar answers"],
    trust: "Post Karo can publish a finished Short to a connected Instagram account after you review and confirm the post. ClipKaro does not publish without your action.",
    faq: [
      { question: "Does ClipKaro post directly to Instagram?", answer: "Yes. Post Karo can publish a finished Short to a connected Instagram Reels account after you review and confirm the post. Post Karo is included on every ClipKaro plan." },
      { question: "Can I make multiple Reels from one video?", answer: "Yes, subject to your plan's Karo Minutes and export limits." },
      { question: "Are captions included?", answer: "ClipKaro supports burned-in subtitles designed for short-form mobile viewing." },
    ],
  },
  {
    slug: SEO_PAGE_SLUGS[5],
    title: "Video to YouTube Shorts India",
    metaTitle: "Video to YouTube Shorts AI in India | ClipKaro AI",
    description: "Convert long creator videos into YouTube Shorts with AI clip suggestions, hooks, titles, captions and vertical exports.",
    eyebrow: "Shorts for YouTube growth",
    h1: "Repurpose your long videos into YouTube Shorts",
    lead: "ClipKaro helps Indian creators discover short moments inside long videos and export vertical clips for YouTube Shorts.",
    audience: "YouTube channels that publish interviews, explainers, education, business advice, podcasts or creator commentary.",
    promise: "Use existing videos to build a Shorts pipeline without starting from zero for every upload.",
    workflow: [
      "Upload the source file from your long-form recording.",
      "Let ClipKaro generate ranked moments and clip titles.",
      "Check context and ending before export.",
      "Publish the finished Short to a connected YouTube account with Post Karo, or download the MP4 for your own workflow.",
    ],
    useCases: ["Channel growth", "Old video repurposing", "Course previews", "Podcast highlights", "Webinar clips", "Niche education"],
    trust: "For best results, use clean source audio and review captions before publishing, especially for mixed-language speech.",
    faq: [
      { question: "Can I repurpose old videos?", answer: "Yes, as long as you own or have permission to process and reuse the source video." },
      { question: "Does it make titles?", answer: "ClipKaro includes generated titles and hook/reason metadata for clip suggestions." },
      { question: "Is it only for YouTube?", answer: "No. Exports can also be used for Instagram Reels and other vertical-video workflows." },
    ],
  },
  {
    slug: SEO_PAGE_SLUGS[6],
    title: "Educational Video to Shorts",
    metaTitle: "Educational Video to Shorts AI | ClipKaro AI",
    description: "Turn lessons, webinars, coaching videos and explainers into short educational clips with AI ranking and captions.",
    eyebrow: "Education clips",
    h1: "Turn lessons and webinars into short educational clips",
    lead: "ClipKaro helps educators and coaches find the clearest teaching moments inside long videos and export them as short vertical clips.",
    audience: "Teachers, course creators, EdTech teams, coaches and consultants who record useful long-form content.",
    promise: "The best educational clips are understandable without the full lecture. ClipKaro helps surface moments with context, value and clean endings.",
    workflow: [
      "Upload a lesson, webinar, workshop or coaching video.",
      "Choose Education or let the AI infer the content type.",
      "Review suggestions for clarity and standalone value.",
      "Export clips for Shorts, Reels, lead magnets or course marketing.",
    ],
    useCases: ["Course previews", "Exam tips", "Explainer clips", "Workshop takeaways", "Coaching advice", "Webinar FAQs"],
    trust: "ClipKaro is most useful when the source video has clean audio and clear speech. Review every educational claim before publishing.",
    faq: [
      { question: "Will viewers understand the clip without the full video?", answer: "That is one of the key checks. ClipKaro ranks for clarity and context, but you should still preview before export." },
      { question: "Can I use this for course marketing?", answer: "Yes. Short teaching moments can become previews, social posts and lead-generation clips." },
      { question: "Does it support Indian education content?", answer: "ClipKaro includes India-first positioning and supports Hindi, Hinglish and English-oriented creator workflows." },
    ],
  },
  {
    slug: SEO_PAGE_SLUGS[7],
    title: "Talking Head Video to Reels",
    metaTitle: "Talking Head Video to Reels AI | ClipKaro AI",
    description: "Convert talking-head videos into short captioned Reels and Shorts with AI moment detection for creators, coaches and founders.",
    eyebrow: "Talking-head repurposing",
    h1: "Convert talking-head videos into captioned Reels",
    lead: "Turn advice, commentary, coaching, lessons and founder videos into short vertical clips with less manual editing.",
    audience: "Creators who record themselves speaking and want more output from each recording session.",
    promise: "ClipKaro focuses on spoken-video moments: strong starts, clear ideas, useful takeaways and natural endings.",
    workflow: [
      "Upload your talking-head recording.",
      "Let ClipKaro find the strongest self-contained moments.",
      "Preview the hook, captions and duration.",
      "Export vertical clips for Shorts or Reels.",
    ],
    useCases: ["Founder advice", "Creator commentary", "Coaching clips", "Personal-brand posts", "Local business tips", "Expert explainers"],
    trust: "Speaker tracking and framing should always be reviewed before publishing, especially when the source video has multiple speakers or unusual framing.",
    faq: [
      { question: "Is this good for coaches and founders?", answer: "Yes. Talking-head advice and story clips are a strong fit for ClipKaro's current workflow." },
      { question: "Do I need editing skills?", answer: "You still choose what to publish, but ClipKaro removes much of the discovery and captioning work." },
      { question: "Can agencies use this for clients?", answer: "Yes. The same workflow works for personal-brand and social-media teams handling client recordings." },
    ],
  },
  {
    slug: SEO_PAGE_SLUGS[8],
    title: "AI Video Clipper India",
    metaTitle: "AI Video Clipper for India — Shorts, Reels & Direct Publishing",
    description: "ClipKaro is an AI video clipper for Indian creators: turn long videos into Shorts with ranked moments, captions, vertical editing and free Instagram + YouTube publishing.",
    eyebrow: "AI video clipper for India",
    h1: "Turn long videos into Shorts with an India-first AI video clipper",
    lead: "ClipKaro helps creators turn long-form video into short-form output without starting from a blank editing timeline. Import a supported YouTube URL or upload the original file, review AI-ranked moments, refine captions and framing, then export or publish the finished Short.",
    audience: "YouTubers, podcasters, educators, coaches, founders, businesses and creator teams in India that already have long-form video and want a faster Shorts and Reels workflow.",
    promise: "The value is the connected workflow: source video → AI-ranked moments → transcript and caption review → vertical edit → export → Post Karo publishing to Instagram Reels or YouTube Shorts.",
    workflow: [
      "Paste a supported YouTube URL or upload an original video file you own or have permission to process.",
      "Let ClipKaro transcribe the source and rank promising self-contained moments.",
      "Review transcript lines, captions, aspect ratio, zoom and framing in Creator Studio.",
      "Export the Short, then publish to a connected Instagram or YouTube account with Post Karo or download the MP4.",
    ],
    useCases: ["YouTube long videos", "Podcasts", "Hindi and Hinglish videos", "Talking-head clips", "Educational videos", "Founder content"],
    trust: "ClipKaro does not guarantee virality or views. It reduces repetitive discovery, captioning and publishing work while keeping the creator responsible for the final clip and post.",
    faq: [
      { question: "What is ClipKaro?", answer: "ClipKaro is an AI video clipper and video repurposing platform that helps creators turn long videos into short clips, review captions and framing, export, and publish finished Shorts to connected Instagram or YouTube accounts." },
      { question: "Can I use ClipKaro for free?", answer: "Yes. The Free plan includes 15 Karo Minutes per month, 2 Shorts per month and Post Karo publishing. Free exports are 720p with a ClipKaro watermark." },
      { question: "Does ClipKaro support Hindi and Hinglish?", answer: "ClipKaro supports Hindi, Hinglish and English-oriented creator workflows. Mixed-language transcript lines should still be reviewed before publishing." },
      { question: "Can ClipKaro publish to Instagram and YouTube?", answer: "Yes. Post Karo can publish finished Shorts to connected Instagram Reels and YouTube Shorts accounts after the creator reviews and confirms the post." },
    ],
  },
  {
    slug: SEO_PAGE_SLUGS[9],
    title: "Post Shorts to Instagram and YouTube",
    metaTitle: "Post Shorts to Instagram Reels & YouTube Shorts with Post Karo",
    description: "Create a Short in ClipKaro, then publish the finished video to connected Instagram Reels or YouTube Shorts accounts with Post Karo, included on every plan.",
    eyebrow: "Post Karo · direct publishing",
    h1: "Create the Short, then post it to Instagram or YouTube from ClipKaro",
    lead: "Post Karo connects the last step of the ClipKaro workflow. After a Short is rendered, a signed-in creator can prepare the post and publish the finished video to a connected Instagram Reels or YouTube Shorts account.",
    audience: "Creators who want fewer handoffs between AI clipping, export and social publishing, while still reviewing every post before it goes live.",
    promise: "Post Karo is included on every ClipKaro plan, including Free. Creation limits still depend on the plan, but publishing access itself is not a paid add-on.",
    workflow: [
      "Create and render the Short in ClipKaro Creator Studio.",
      "Open Post Karo from the finished export.",
      "Choose a connected Instagram or YouTube account and review the publishing draft.",
      "Confirm the post. ClipKaro sends the finished Short through the connected publishing service and reports the result.",
    ],
    useCases: ["Instagram Reels", "YouTube Shorts", "Creator workflows", "Podcast clips", "Educational Shorts", "Founder content"],
    trust: "Post Karo requires an account connection and an explicit publishing action. ClipKaro does not silently publish content and does not guarantee reach, engagement or virality after a post goes live.",
    faq: [
      { question: "Is Post Karo free?", answer: "Yes. Post Karo is included on every ClipKaro plan, including Free." },
      { question: "Which platforms can Post Karo publish to?", answer: "The current Post Karo workflow supports connected Instagram Reels and YouTube Shorts accounts." },
      { question: "Does ClipKaro publish without asking me?", answer: "No. The creator reviews the publishing draft and confirms the post." },
      { question: "Do plan limits still apply?", answer: "Yes. Karo Minutes, Short creation limits, resolution and watermark rules still depend on the selected plan. Post Karo publishing access itself is included on every plan." },
    ],
  }
];

export function getSeoPage(slug: string) {
  return SEO_PAGES.find((page) => page.slug === slug);
}
