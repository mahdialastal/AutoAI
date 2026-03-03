# Feature parity: AutoAI vs Klap, Opus Clip, Vidyo, and similar apps

This document maps what commercial “long video → shorts” apps do and how AutoAI compares, so the app can **do what they do**—fully locally.

---

## How those apps work (workflow & UX)

| App | Main flow | Layout / reframe |
|-----|-----------|------------------|
| **Klap** | 1) Upload video 2) Convert with AI 3) Export & share. No layout choice in the main flow. | Smart reframing is **automatic**; AI selects engaging moments and reframes for vertical. Customization (captions, colors, aspect ratio) in the editor. |
| **Opus Clip** | Paste URL / upload → AI generates clips. Layout is set in **Clip layout settings** (brand template) or per clip. | User picks **layout by name**: Gameplay (30% speaker top, 70% gameplay bottom), Screenshare (screen top, speaker bottom), Split, Fill, Fit, Three, Four. Manual reframe = Crop icon or double‑click for fine‑tune. |
| **Vidyo** | Paste URL or upload → AI generates clips → edit (trim, captions, templates). | **CutMagic** auto‑crops and keeps speaker in focus. Aspect ratio + template first; manual resize/crop available. |
| **Dumme** | 1) Upload 2) AI finds highlights 3) Get shorts (captions, titles, descriptions). | Fully **automatic**; no layout selection. |
| **2short** | Upload → AI creates shorts. | **Face tracking** keeps speaker centered automatically; no drawing or sliders. |
| **AutoShorts (this app)** | Paste URL or upload → **Layout** (Auto / Streaming / Split / Speaker) + Source (full / screen recording) → Generate. | **Auto** = detect streaming vs speaker from first frame. **Streaming** = face + chat, webcam on top, chat on bottom. **Split** = bottom left/right stacked. **Speaker only** = face‑tracked center. **Source**: Screen recording = crop to center 70% first (for browser/embed). No sliders; manual crop via CLI only. |

Takeaway: **No app uses sliders or “draw a box” in the main flow.** They use either full auto (Klap, Dumme, 2short) or **named layout presets** (Opus, Vidyo). AutoShorts matches that: one Layout dropdown with presets, Generate, done.

---

## Per-app workflow (all 18 checked)

| App | Input | Main steps | Layout / reframe | Output |
|-----|--------|------------|------------------|--------|
| **Klap** | Upload or URL (YouTube, S3, etc.) | Upload → Convert with AI → Export | Auto reframe; AI keeps subject in frame. No layout pick in main flow. | Shorts, captions, vertical; share/schedule |
| **2short AI** | Paste YouTube URL or upload | Paste link → AI analyzes → clips | Face tracking keeps speaker centered. Weak on screen recordings (41% accuracy). | 1080p Shorts/Reels/TikTok, animated subs |
| **Dumme** | Upload or YouTube/Spotify/Twitter | Upload → AI finds highlights → Get shorts | Fully automatic; no layout choice. | Shorts with captions, titles, descriptions |
| **Munch** | Long-form video | Upload → AI finds viral moments | Algorithm-optimized metadata; clip selection. | Trend-aware clips, explanations |
| **Opus Clip** | URL (YouTube, Drive, Vimeo, Zoom, Twitch…) | Paste URL → AI generates clips | **Layout by name**: Gameplay, Screenshare (auto-detects), Split, Fill, Fit, Three, Four. Manual reframe = Crop / double-click. | Platform-ready 9:16 / 16:9 / 1:1 |
| **Qlip** | Podcasts, long video, streams | Upload → AI spots highlights | Vertical/square, subtitles, speaker ID, branding. | Social-ready clips, publish |
| **Spikes Studio** | Video (Twitch, YouTube, TikTok…) | Upload → AI clipping | Best moments → Shorts/Reels/Twitch; integrations. | Multiple clips, auto-captions, hashtags |
| **Vidyo** | Paste URL or upload | Import → AI generates clips → edit | **CutMagic** auto scene detection; speaker in focus; aspect ratio + template. | Trim, captions, resize; schedule |
| **Vizard AI** | Long-form video | Upload → AI editing | Auto subtitles, translation (100+ langs), speaker tracking, brand templates. | Shorts, text-based editing |
| **Ssemble** | Video (part of broader editor) | In editor: clip generation | Repurposing and clip generation. | Clips within editor workflow |
| **Veed.io** | Upload (browser) | Upload → edit | Auto subtitles, trim, zoom, b-roll, transitions. Caption-focused. | Edited video, captions |
| **Submagic** | Video (API or app) | Upload → Magic Clips / auto-zoom | Viral captions 48+ langs, AI avatars, auto-zoom, auto-cuts, b-roll. | 4K/60fps, captions |
| **Zubtitle** | Upload | Upload → transcribe → resize | Auto transcribe, caption styles, headlines, progress bars, resize for social. | Captioned, resized video |
| **Wisecut** | Video | Upload → AI edit | **Facial recognition auto reframe**; multi-face focus; silence cut; storyboard/edit-by-transcript. | Auto captions, translations, music |
| **LiveLink** | YouTube URL | Paste URL → Create Clips | AI finds moments, trim silence, resize, auto captions, hashtags. | Shorts, transcript |
| **SendShort** | Video | Upload → AI moments | AI detection, auto subtitles, faceless/series, manual edit. | Clips, free tier |
| **Short.ai** | URL or upload | Paste URL / upload → AI | Smart AI cropping (9:16, 1:1), virality score, B-roll, brand kit, scheduler. | 10+ clips, multi-platform |
| **Nexus Clips** | YouTube, Twitch | Connect → clip | "Clip this" voice command, auto titles/descriptions/hashtags, text/stickers. | Unlimited clips |
| **AutoShorts** | YouTube URL or upload | Paste URL / upload → set number of shorts → (optional: Layout, Source) → Generate | **Auto** = detect streaming vs speaker from first frame. **Streaming** = webcam top, chat bottom. **Split** / **Speaker only**. **Source**: full frame or screen recording (crop to center 70%). | 9:16 shorts, captions, local only |

---

## What those apps do (summary)

| App | Core offering |
|-----|----------------|
| **Klap** | AI clip detection (tone, hooks, statements), auto reframe (split/gaming layouts), captions 52 langs, vertical export, customize fonts/colors/logo, export or schedule. |
| **Opus Clip** | ClipAnything (any genre), ReframeAnything (keep subject centered), virality score, multi-clip from one video, platform-ready export. |
| **Vidyo / Quso** | AI clipping + virality score, captions, social scheduling, templates, speaker tracking for vertical. |
| **Vizard AI** | Long→short, auto subtitles + translation (100+ langs), text-based editing, brand templates, speaker tracking. |
| **Dumme** | Finds clip-worthy moments, keeps context, captions + titles + descriptions for algorithms, 8–12 clips per 20 min. |
| **2short AI** | Best moments → Shorts/Reels/TikTok, face tracking, animated subtitles, 1080p, aspect ratios, brand presets. |
| **Munch** | Long-form → clip-worthy moments, algorithm-optimized metadata and formatting. |
| **Qlip** | AI highlights (semantics, sentiment, tone, visual), vertical/square, subtitles + speaker ID, branding (logo, fonts, colors), publish to social, team workspace. |
| **Spikes Studio** | Best moments → TikTok/Shorts/Reels/Twitch, integrations (YouTube, TikTok, etc.), micro-drama engine. |
| **Ssemble** | Clip generation and repurposing (part of broader editor). |
| **Veed.io** | Online editor: auto subtitles, trim, b-roll, transitions, zoom; caption-focused. |
| **Submagic** | Viral captions 48+ langs, Magic Clips (key moments), AI avatars, auto-zoom, auto-cuts, b-roll, 4K/60fps export. |
| **Zubtitle** | Auto transcribe, caption styles, headlines, progress bars, resize for social. |
| **Wisecut** | Auto-cut silences, AI highlight detection, auto reframe, auto captions/translations, smart music, storyboard/edit-by-transcript. |
| **LiveLink** | Clip maker: NLP + audio, best moments, trim silence, resize, auto captions, hashtags, transcript. |
| **SendShort** | AI moment detection, auto subtitles, faceless/series, manual edit, free tier. |
| **Short.ai** | One video → 10+ clips, virality score (hooks, flow, value, trends), captions, B-roll, faceless from text, multi-platform publish, brand consistency. |
| **Nexus Clips** | Smart moment detection, “clip this” voice command, auto titles/descriptions/hashtags, unlimited from YouTube/Twitch, text/stickers/effects. |

---

## Unified feature list (what “doing what they do” means)

Grouped into **input → processing → editing → export → publishing**.

### 1. Input & source

| Feature | AutoAI now | Gap / note |
|--------|------------|------------|
| YouTube URL | ✅ yt-dlp | — |
| Local file upload | ✅ CLI + Gradio | — |
| Podcast / audio | ✅ Same pipeline (video or audio) | — |
| Screen recording / region | ✅ Manual crop, center pre-crop, optional bbox | — |

### 2. Transcription & language

| Feature | AutoAI now | Gap / note |
|--------|------------|------------|
| Speech-to-text with timestamps | ✅ faster-whisper | — |
| Auto language detection | ✅ Whisper | — |
| Multi-language / translated captions | ⚠️ Doc only (Ollama/argos) | **Add:** optional translate SRT then burn (e.g. Ollama or argos-translate). |
| Speaker labels in transcript | ❌ | Optional: diarization (pyannote or Whisper speaker tags if available). |

### 3. Highlight / clip detection (“AI finds the best moments”)

| Feature | AutoAI now | Gap / note |
|--------|------------|------------|
| Pick N segments from transcript | ✅ Ollama (hooks, punchy, 15–60 s) | — |
| Virality / engagement score per clip | ❌ | **Add:** LLM or simple heuristic score (hook strength, length, punch) and show in UI / use for ordering. |
| Avoid silent or dead segments | ❌ | **Add:** silence detection (e.g. pydub/silence), filter or trim in pipeline. |
| Topic / chapter awareness | ⚠️ Chunk-based only | Optional: chapter boundaries or topic segments for smarter boundaries. |

### 4. Vertical reframing & crop

| Feature | AutoAI now | Gap / note |
|--------|------------|------------|
| 9:16 vertical export | ✅ | — |
| Center crop | ✅ | — |
| Face / speaker tracking (keep speaker in frame) | ✅ MediaPipe focus_x | — |
| Multiple layouts (split, bottom strip, stack) | ✅ bottom_split_stack, etc. | — |
| User-defined crop region (sliders or draw) | ✅ Sliders + optional bbox annotator | — |
| “ReframeAnything”-style auto reframe | ⚠️ Center + face | Could extend with better face/torso tracking. |

### 5. Captions & on-screen text

| Feature | AutoAI now | Gap / note |
|--------|------------|------------|
| Burned-in subtitles (SRT) | ✅ FFmpeg subtitles | — |
| Styled captions (font, color, position) | ❌ Plain SRT→subtitle filter | **Add:** ASS styling or caption template (e.g. bold, size, safe area). |
| Animated / word-by-word captions | ❌ | Optional: karaoke-style ASS or dedicated caption renderer. |
| Multiple caption languages in one export | ❌ | Optional: multi-track or multiple exports. |

### 6. Export & quality

| Feature | AutoAI now | Gap / note |
|--------|------------|------------|
| MP4, 9:16, H.264 | ✅ | — |
| Resolution / bitrate control | ⚠️ Fixed 1080×1920 | **Add:** CLI/UI option for resolution and maybe bitrate. |
| 4K / 60fps | ❌ | Optional: pass-through or encode options. |

### 7. Metadata & publish-ready output

| Feature | AutoAI now | Gap / note |
|--------|------------|------------|
| Per-clip title / description / hashtags | ❌ | **Add:** LLM-generated title + description + hashtags per short (save to .txt or .json next to each file). |
| Filename reflects content | ⚠️ short_1, short_2 | Optional: slug from title. |

### 8. Publishing (out of scope for “local-first”)

| Feature | AutoAI now | Gap / note |
|--------|------------|------------|
| Direct post to YouTube / TikTok / etc. | ❌ | Intentionally local-only; users upload manually. |
| Scheduling | ❌ | Same. |

### 9. Extra (nice-to-have)

| Feature | AutoAI now | Gap / note |
|--------|------------|------------|
| B-roll insertion | ❌ | Complex; lower priority. |
| Auto background music | ❌ | Licensing + ducking; lower priority. |
| Text-based / storyboard editing | ❌ | Bigger UX; optional later. |
| Brand templates (logo, fonts, colors) | ❌ | **Add:** optional logo overlay + configurable caption style. |
| Team / collaboration | ❌ | Out of scope for local app. |

---

## Prioritized roadmap (to “do what they do”)

### Phase 1 – High impact, local-friendly

1. **Virality / quality score per clip**  
   - Use Ollama to score each selected segment (hook, clarity, length) and optionally sort or show score in UI.  
   - **Deliverable:** Score in pipeline, show in Gradio (e.g. “Clip 1 – Score: 8/10”).

2. **Auto-cut silences**  
   - Detect silent stretches (e.g. pydub or ffmpeg silence detect), trim or mark segments so highlights avoid long silence.  
   - **Deliverable:** Optional `--trim-silence` (or UI toggle), segment boundaries avoid silence.

3. **Per-clip metadata (title, description, hashtags)**  
   - For each short, call Ollama to generate title, short description, and 3–5 hashtags; write to `short_1_meta.txt` (or .json) next to each MP4.  
   - **Deliverable:** Files like `short_1.mp4` + `short_1_meta.txt` (or .json) with title, description, hashtags.

4. **Optional translated captions**  
   - Add a “Translate captions to” language option; use Ollama (or argos-translate) to translate the SRT, then burn the translated SRT.  
   - **Deliverable:** CLI/UI “Caption language” / “Translate to”, second SRT + burn.

### Phase 2 – Polish

5. **Caption styling**  
   - Support ASS or a simple template (font size, bold, safe area) so burned captions look more like Submagic/Zubtitle.  
   - **Deliverable:** Configurable caption style (e.g. `--caption-style bold`) and/or ASS.

6. **Resolution / quality options**  
   - CLI and UI options for output resolution (e.g. 1080×1920 vs 720×1280) and optionally bitrate.  
   - **Deliverable:** `--resolution`, UI dropdown.

7. **Branding: logo overlay**  
   - Optional logo image + position (e.g. corner) overlaid on each short via FFmpeg.  
   - **Deliverable:** `--logo path` and position (e.g. top-right).

### Phase 3 – Optional

8. **Speaker labels in transcript**  
   - Integrate diarization (e.g. pyannote) or use Whisper speaker segments if available; show “Speaker 1: …” in transcript/UI.  
9. **B-roll / music**  
   - Only if you want to approach Submagic/Short.ai level; higher complexity and licensing.  
10. **Text-based editing**  
   - Edit by editing transcript and re-run cut list (like Wisecut storyboard); larger UX change.

---

## Summary

- **Already aligned with “what they do”:** YouTube/local input, transcription, AI highlight selection, vertical reframing, face-aware crop, multiple layouts, manual crop region, burned-in captions, 9:16 export.  
- **Next steps to match them:** virality score, trim silences, per-clip title/description/hashtags, optional translated captions, then caption styling, resolution options, and optional logo overlay.  
- **Intentionally out of scope:** direct publish/scheduling (stay local), team features, faceless text-to-video.

Using this roadmap, AutoAI can **do what Klap, Opus Clip, Vidyo, Dumme, 2short, Munch, Qlip, Spikes Studio, Vizard, Ssemble, Veed, Submagic, Zubtitle, Wisecut, LiveLink, SendShort, Short.ai, and Nexus Clips do** in terms of core long→short workflow, while remaining 100% local and open.
