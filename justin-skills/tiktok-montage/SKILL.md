---
name: "tiktok-montage"
description: "Use to cut a user's real video clips into one TikTok video with caption and hashtags, post it, and learn from like/dislike feedback. No AI-generated footage."
---

# TikTok Montage — Skill x0.2

Cut a user's real clips into one professional TikTok video with FFmpeg. Write a caption. Add the user's hashtags. Post through the user's TikTok connection. Learn from each "I like" / "I don't like" and write it into that user's own Style Spec, so the next video is closer to correct the first time.

This skill is shared. Each user has their OWN Style Spec, their OWN TikTok connection, and their OWN clips. Never read or write another user's Style Spec.

## Requirements (check at the start of each run)

| Need | Check | If missing |
|---|---|---|
| Code execution + FFmpeg | `which ffmpeg ffprobe` | `pip install static-ffmpeg --break-system-packages && static_ffmpeg_paths`; if that fails, tell the user FFmpeg is not available and stop |
| Access to clips | connected folder (desktop app) or uploads | Tell the user: open the chat in the Claude desktop app, + → Add folder. A cloud drive works if its desktop sync app syncs it to that computer. For a few short clips, upload in chat |
| Posting (optional) | Higgsfield connector with `tiktok_accounts` | Deliver the MP4 + caption text for manual upload in the TikTok app |
| Python libs (optional) | `python3 -c "import cv2"` | `pip install opencv-python-headless --break-system-packages`; if it fails, skip sharpness scoring and say so |

## Hard rules

1. Use ONLY the clips the user supplies. Do NOT generate, extend, inpaint, upscale, or change footage with AI. Higgsfield is only the hosting and TikTok publish pipe.
2. Put music into the file ONLY if the user states they own or licensed the track. Otherwise the user adds music in the TikTok publish form (licensed library).
3. Do NOT post before the user approves the cut. Posting always needs the user to submit the TikTok publish form.
4. Use the user's hashtags exactly. Add others only if their Style Spec permits it.
5. Copy clips into the workspace. Never change, move, or delete the user's original files.
6. If information is necessary and it is not in the Style Spec or the request, ask. Do not guess.

## Style Spec (per user, stored outside this skill)

The Style Spec holds everything that is taste. The skill holds only the procedure. The skill reads the Style Spec at the start of every run and writes to it after every piece of feedback. No skill re-save is needed for style changes.

**Location (ask once on first run, then record it in the Spec header):**
- Default: `tiktok-montage-style-spec.md` in the user's connected clips folder (works for anyone).
- Option: a Notion page named `TikTok Montage — Style Spec`, if the user has Notion connected and asks for it.
- If neither is available (uploads only): keep it in the workspace, send it to the user at the end of the run, and ask them to upload it next time.

**First run:** if no Style Spec exists, create it from this template, then ask only for the items marked (ask).

```markdown
# TikTok Montage — Style Spec x0.1
Owner: (ask: name or handle)
Status: LEARNING   # becomes LOCKED when the user says the style is final

## Settings
- Explanation style: plain, short. (default)
- File names: <slug>_x0.N.mp4; drop the x when LOCKED. (default)
- Format: 1080x1920, 9:16, 30 fps, H.264 High, yuv420p, AAC 48 kHz 192k, MP4 faststart. (default)
- Framing: fill + center crop; move crop toward the subject when the subject is off-center. (default)
- Target length: 30-60 s. (default)
- Hook: strongest shot first, 1-2 s. (default)
- Clip order: user order, except the hook. (default)
- Shot length: 1.5-4 s; longer only for speech. (default)
- Transitions: hard cuts on action; 0.25 s crossfade only at scene changes. (default)
- Cuts: never inside a spoken word. (default)
- Audio: original clip audio; final mix -14 LUFS, -1 dBTP. (default)
- Music: added by user in TikTok publish form. (default)
- On-screen text: none. (default)
- Subtitles: off. (default)
- Color: no grade; match exposure if clips differ a lot. (default)
- Caption voice: (ask) e.g. short, warm, cute, 1-2 lines, 0-2 emoji
- Caption length: caption + hashtags <= 150 chars; overflow to description. (default)
- Hashtag sets: (ask)
- Extra hashtags allowed: no. (default)
- Privacy: (ask)
- Comments / Duet / Stitch: (ask)
- Post mode: DIRECT_POST after approval. (default) Option: UPLOAD_TO_DRAFT
- A/B variants: on while LEARNING, off when LOCKED. (default)

## Feedback log
| Date | Video | Said | Applied as | Scope |
|---|---|---|---|---|

## A/B choices
| Date | Video | A | B | Picked | Difference tested |
|---|---|---|---|---|---|

## Results (optional)
| Date | Video | Views | Avg watch s | % full watch | Notes |
|---|---|---|---|---|---|
```

## Procedure

Use a task list. Tracer-bullet: one thin end-to-end pass first, then improve.

### 0. Load
- Run the Requirements checks.
- Find and read the user's Style Spec (or create it, see above). Apply every setting. Items still marked (default) are allowed; items marked (ask) must be answered before the edit.

### 1. Intake
- Copy clips into `work/src/`. Get hashtags and the topic/audience (for the caption).
- Probe every clip:
```bash
mkdir -p work/probe
for f in work/src/*; do ffprobe -v error -show_entries stream=codec_type,width,height,r_frame_rate:stream_side_data=rotation:format=duration -of json "$f" > "work/probe/$(basename "$f").json"; done
```
- Note rotation, missing audio, variable frame rate, very short clips.

### 2. Analyze (measurement only, no AI generation)
For each clip, write `work/analysis/<clip>.json` with:
- Scene changes: `ffmpeg -i IN -vf "select='gt(scene,0.3)',showinfo" -f null - 2>&1 | grep -o 'pts_time:[0-9.]*'`
- Black frames: `ffmpeg -i IN -vf blackdetect=d=0.1:pix_th=0.10 -f null - 2>&1 | grep black_start`
- Frozen frames: `ffmpeg -i IN -vf freezedetect=n=0.003:d=0.5 -f null - 2>&1 | grep freeze_start`
- Exposure per 0.5 s: `ffmpeg -i IN -vf "fps=2,signalstats,metadata=print:key=lavfi.signalstats.YAVG" -f null - 2>&1 | grep YAVG`
- Silence / speech gaps: `ffmpeg -i IN -af silencedetect=n=-35dB:d=0.3 -f null - 2>&1 | grep silence_`
- Sharpness per 0.5 s (if OpenCV): variance of Laplacian on grayscale frames; low = blurry.
- Shake per 0.5 s (if OpenCV): std-dev of frame-to-frame shift from `cv2.phaseCorrelate`; high = shaky.
- Thumbnail sheet for visual inspection: `ffmpeg -v error -i IN -vf "fps=2,scale=180:-1,tile=8x4" -frames:v 1 work/thumbs/<clip>.png`, then Read it.

Shot score = sharp + stable + good exposure + has motion or a clear subject, minus black/frozen. Read the thumbnail sheets before trusting the numbers.

Optional, only if the Style Spec turns them on:
- Subtitles: `pip install faster-whisper --break-system-packages`. If the model download is blocked, say so and continue without subtitles.
- Beat sync (licensed track only): `pip install librosa --break-system-packages`; `librosa.beat.beat_track` → cut points on beats.

### 3. Edit decision list
- Pick the best window of each clip. Start/end cuts in silence gaps, never inside a word.
- Put the hook shot first. Fit the target length.
- Write `work/edl_A_x0.N.csv`: `order,file,in_s,out_s,transition_out`.
- If A/B is on: write `work/edl_B_x0.N.csv` that changes ONE dimension only (pacing, order, transitions, hook, or framing). Record which one.

### 4. Build segments
```bash
VF="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p,setsar=1"
# clip with audio
ffmpeg -y -ss IN_S -to OUT_S -i SRC -vf "$VF" -af "aresample=48000,aformat=channel_layouts=stereo" -c:v libx264 -preset veryfast -crf 18 -c:a aac -b:a 192k work/seg/A_NNN.mp4
# clip without audio: add silence
ffmpeg -y -ss IN_S -to OUT_S -i SRC -f lavfi -i anullsrc=r=48000:cl=stereo -vf "$VF" -map 0:v -map 1:a -shortest -c:v libx264 -preset veryfast -crf 18 -c:a aac -b:a 192k work/seg/A_NNN.mp4
```
For an off-center subject, replace the center crop with `crop=1080:1920:X:0` (compute X after the scale).

### 5. Assemble and finish
- Hard cuts only:
```bash
ls work/seg/A_*.mp4 | sed "s/^/file '/;s/$/'/" > work/list_A.txt
ffmpeg -y -f concat -safe 0 -i work/list_A.txt -c copy work/assembled_A.mp4
```
- With crossfades: chain `xfade` + `acrossfade`. offset for each join = sum of earlier segment durations (from ffprobe) minus sum of earlier fade durations.
- Finish:
```bash
ffmpeg -y -i work/assembled_A.mp4 -af "loudnorm=I=-14:TP=-1:LRA=11" -c:v libx264 -preset veryfast -crf 18 -profile:v high -pix_fmt yuv420p -c:a aac -b:a 192k -ar 48000 -movflags +faststart out/<slug>_A_x0.N.mp4
```
- On-screen text or subtitles: `drawtext` / `subtitles` here, inside the TikTok safe area (not in the bottom 20% or right 12%).
- Do the same for B if A/B is on.

### 6. Verify (all, for each output)
- Contact sheet, then Read it: `ffmpeg -v error -i FILE -vf "fps=1,scale=216:-1,tile=6x10" -frames:v 1 FILE_sheet.png`. Look for bad crop, black frames, jump cuts, repeated shots, text outside safe area.
- TikTok limits (ffprobe): MP4, 3-600 s, 23-60 fps, <= 1 GB, both sides >= 360 px.
- Loudness: `ffmpeg -i FILE -af ebur128 -f null - 2>&1 | tail -12` → about -14 LUFS.
- Length in the target range. Hook in the first 2 s.

### 7. Review
- Send the video(s) and contact sheet(s) with SendUserFile. If A/B, say in one line what is different.
- Send the caption + hashtags as text.
- Ask: which one, and what do you like / not like? Do not post without approval.

### 8. Post
1. `tiktok_accounts`. No `active` account → `tiktok_connect`, give the link, wait, check again.
2. Upload the approved file: `media_upload` → `curl -T FILE "UPLOAD_URL"` → `media_confirm`. Use the hosted URL.
3. `tiktok_prepare_publish`: VIDEO; mode from the Style Spec; caption + hashtags in `title` (<= 150 chars), overflow in `description`; `is_aigc: false` (rule 1 makes this true); privacy and toggles only from the Style Spec or the user.
4. Tell the user to review and submit the publish form, and to add music there if wanted. If the form does not show (some mobile apps), tell them to open the chat on claude.ai on a computer.
5. After submit: `tiktok_publish_status` until live or failed. Report the result.
6. If posting is not available: deliver the MP4 and the caption text for manual upload.

### 9. Results (optional, if the user wants it)
About 48 h after a post, ask the user for views, average watch time, and % watched to the end (a screenshot of TikTok analytics is fine). Add a row to Results. After 5 or more rows, suggest Style Spec changes that the numbers support. Apply only the ones the user confirms.

## Feedback loop (automatic)

After every reply that contains a like, a dislike, an A/B pick, or a change request:
1. Apply it to the current video. Bump the video version (x0.1 → x0.2). Do steps 5-7 again.
2. Decide the scope: THIS video only, or a standing rule? Clear standing signals: "always", "never", "I like it when", "I hate", a repeat of earlier feedback, the same A/B choice 2 times. If not clear, ask one short question.
3. Standing rule → write it into the user's Style Spec now: change or add the setting line, remove "(default)" or "(ask)" from lines the user confirmed, bump the Spec version, add a Feedback log row. A/B pick → add an A/B row; after 2 picks in the same direction, update the setting.
4. Tell the user in one line what changed in their Style Spec.
5. Procedure changes (not taste) need a skill change. Only the skill owner can do that, through `propose_skills`. Never put one user's taste into this skill.
6. When the user says the style is final ("lock it", "that's the one"): set Status: LOCKED, drop the x from the Spec version (v1.0), turn A/B off. After that, ask only for clips, hashtags (if new), and topic. Still log feedback; a LOCKED Spec changes only when the user asks.

## Automatic drafts (optional)
If the user asks: create a scheduled task that needs their computer, checks a `To Edit` folder, makes a draft cut of new clips with steps 0-7, and notifies them. It never posts.

## Change log
- x0.2 — Shareable: Style Spec moved out of the skill into a per-user file or Notion page that updates automatically from feedback. Added requirement checks, measured shot scoring, hook-first, no cuts inside words, A/B variants, optional subtitles, beat sync, results loop, automatic drafts.
- x0.1 — First version.