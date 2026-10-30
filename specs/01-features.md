# 01 — Research and feature set

## How the best apps auto-edit

Every leading auto-editor follows the same three steps: analyze the media and music, build a story or "script" of the edit, then apply a style.

| App | How its auto edit works | What we copy |
| --- | --- | --- |
| [CapCut AutoCut](https://www.capcut.com/help/why-cant-i-use-auto-cut) | Trims and syncs clips to music beats, speech pauses or text prompts; Auto-Edit became the default first step for new projects in 2026 | Beat Cut / Rhythm Edit, one-tap paced cut, auto captions |
| [Captions AI Edit](https://captions.ai/tools/ai-video-editor) | LLM-driven video understanding; user picks a style and AI adds zooms, transitions, B-roll, graphics, captions and music; a chat editor takes plain-language changes | Style presets, prompt-based "edit like you text" control |
| [GoPro Quik](https://apps.appfollow.io/ios/gopro-quik/561350520?country=gb) | Finds the best shots in an album of photos and videos, syncs them to music, adds transitions and themes | Highlight detection, beat sync of cuts, transitions and effects, multi-segment speed tool |
| [Magisto](https://help.magisto.com/hc/en-us/articles/360023438791-What-is-Magisto-) | Emotion Sense analyzes motion speed, faces, close-ups and audio, then writes a story for the final cut | Emotion and motion scoring to rank moments, story arc |
| [DaVinci Resolve 20](https://www.ravepubs.com/blackmagic-design-announces-davinci-resolve-20-with-over-100-new-features-and-ai-powered-tools) | AI beat detection with snapping, IntelliScript timelines, Multicam SmartSwitch, AI Audio Assistant mix | Beat markers, auto audio mix, keyframe engine |
| [Adobe Premiere Pro](https://news.adobe.com/news/2025/04/new-ai-innovation-in-industry) | Media Intelligence tags objects, locations and camera angles; Auto Reframe, Scene Edit Detection, Music Remix, Generative Extend | Content tagging and search, auto reframe to any ratio, music remix to fit length |

The common thread: an analysis layer that scores every moment, a planner that maps moments to the music's structure, and a style engine.

## Feature list

| Category | Feature | What it does in the edit |
| --- | --- | --- |
| Music | Beat, downbeat and drop detection | Every cut, flash and shake lands on a beat; big moments land on drops |
| Music | Energy curve and sections | Intro, build, drop, break, outro drive pacing |
| Music | Music remix to length | Trims the track to fit the edit cleanly on a downbeat |
| Analysis | Highlight scoring | Ranks every moment by motion, faces, sharpness, aesthetics and action |
| Analysis | Scene and shot detection | Splits raw clips into usable shots |
| Analysis | Media tagging | Labels objects, places and camera angles so prompts like "use the car shots" work |
| Motion | Velocity edit (speed ramps) | Fast-to-slow-mo curves on drops with smooth frame interpolation |
| Motion | Freeze frames and reverse | Freeze on impact, rewind hits |
| Motion | Keyframed zoom, spin, shake | Punch-in zooms, camera shakes and spins with easing curves |
| Motion | Motion blur | Directional blur during fast moves and transitions |
| Transitions | Zoom, whip, spin, glitch, flash, luma fade | Picked per beat by the brain |
| Visual FX | Flash, glow, light leaks, RGB split, chromatic aberration, VHS, film grain | Beat-triggered hits and texture |
| Visual FX | Color grade presets and LUTs | Cinematic, teal-orange, moody, vibrant, B&W |
| Subject | Cutout and text-behind-subject | Titles sit behind the person |
| Subject | Motion tracking | Text and effects stick to a moving subject |
| Photos | Ken Burns and 2.5D parallax | Photos get depth-based camera moves so they feel like video |
| Framing | Smart auto reframe | One edit exported to every ratio with the subject kept in frame |
| 360 | Virtual camera, beat spin, tiny planet, rabbit hole, FOV punch | See `08-osmo360.md` |
| Quality | AI upscale | 4K, 6K and 8K output with restored detail |
| Quality | Frame rate conversion | 24, 30 or 60 fps via interpolation |
| Text | Animated titles and kinetic text | Text pops on beats; auto captions if there is speech |
| Audio | Auto mix and ducking | Music levels, SFX whooshes on transitions, speech kept clear |
| Control | Style presets | Velocity, Hype, Cinematic, Anime-style, Travel, Car edit, Sports |
| Control | Prompt control | Plain-language instructions mapped onto the edit plan |
| Control | Variations | Several different edits from the same inputs |
