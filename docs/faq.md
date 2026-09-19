# Frequently Asked Questions

## 1. Use cases

### What kinds of videos is LaunchFrame best suited for?

LaunchFrame is designed for **structured promotional and explanatory videos** built from existing product documentation. It works best when:

- The subject is a software product, platform, service, or technical project.
- Source materials already exist: Markdown files, PDFs, Word documents, PPTX decks, spreadsheets, screenshots, or architecture diagrams.
- The video format is a narrated slide presentation — title slide, key features, architecture, roadmap, call to action.
- The audience is internal (team demos, management reviews, onboarding) or external (product landing pages, conference recordings, release announcements).
- Bilingual delivery is needed: a primary English track and one configurable secondary language in the same video.
- The team needs a repeatable, auditable workflow: every stage produces reviewable artifacts before the next one starts.

Typical run times: **3 to 20 minutes**. Shorter runs (under 3 minutes) work but leave little room for meaningful narration per slide. Longer runs (over 20 minutes) are possible but cost more LLM tokens and Azure Speech time, and the review cycle becomes heavier.

---

### What is it NOT suitable for?

| Not suitable | Reason |
|---|---|
| Live-action or talking-head video | No camera capture, no video editing |
| Screen recording and demo walkthroughs | No screen capture; reference videos can inform content but are not embedded |
| Marketing creative / brand advertising | LLM output is factual and structured, not copywriting |
| Narrative / story / entertainment video | No script for non-presentation formats |
| Background music or sound effects | Audio pipeline is narration-only |
| Real-time streaming or live publishing | Outputs are local files; publishing is manual |
| Automatic publishing to any platform | Intentionally out of scope; users upload manually |
| More than two languages in a single video | One primary (English) and one secondary language per run |
| Fully automated unattended generation | Every run requires at least Draft approval before video is built |

---

### How much source material is needed?

A minimum of **one supported content file** (document, image, table, PDF/DOCX, or PPTX) is required to start a build. The LLM generates a richer outline when more material is available.

Practical guidance:

- **Thin material** (one short Markdown file): the LLM will produce a short, generic draft. Supplement with bullet-point notes, a screenshot, or a brief PPTX.
- **Rich material** (multiple docs, images, PPTX, video with subtitles): the LLM can produce a detailed, well-structured draft aligned with existing content.
- **Too much material**: the LLM context window has a limit. If the total text of all content files exceeds roughly 50–100 KB of plain text, consider splitting the project into smaller focused videos or pruning less relevant documents.

---

## 2. Dependencies and limitations

### What external services are required?

| Service | Required for | Notes |
|---|---|---|
| **Azure AI Speech** | Audio synthesis, subtitles, video | Mandatory. No Speech resource = no audio, subtitles, or video. PPT and PDF review still work. |
| **LLM Provider** (OpenAI/OpenAI-compatible by default; optional providers) | Draft generation, Vision analysis | Mandatory for Draft. Vision is optional. |
| **Pi** | LLM and Vision orchestration in the Web GUI | Auto-starts when a directory is loaded. Not required for direct CLI use. |

None of these services are created by LaunchFrame. Azure Speech resources must be provisioned by an authorized Azure administrator before use.

---

### Is Vision analysis required?

No. Vision is **optional**. When disabled or skipped:

- Image files are still listed in the resource scan and their filenames are included in the LLM prompt.
- PPTX slide text and video transcripts are still extracted and sent to the LLM.
- The Draft and all downstream stages proceed normally.

Enable Vision when product images, diagrams, or slide screenshots carry visual information that is not captured in text form.

---

### What local software must be installed?

| Software | Required | Purpose |
|---|---|---|
| **FFmpeg** | Yes | Audio normalization, atempo fit, video rendering |
| **Pi** | Yes (Web GUI) | LLM and Vision orchestration |
| **Python 3.10+** | Yes | Runtime |
| **Microsoft PowerPoint Desktop** | Recommended (Windows; supported on macOS through automation) | PPTX→PDF rendering; automatic in `VIDEO_RENDERER=auto` when detected |
| **Microsoft Word / Excel for Mac** | Optional | DOCX/XLSX→PDF rendering for Vision when installed |
| **LibreOffice** | Fallback | Office-to-PDF conversion when native Office automation is unavailable |
| **Poppler (`pdftoppm`)** | Fallback | PDF→PNG slide frames when LibreOffice renderer is used; macOS PowerPoint uses PyMuPDF instead |
| **Azure CLI (`az`)** | Recommended | `DefaultAzureCredential` via `az login`; other credential sources also work |

FFmpeg is not included in the source repository, and Git LFS is not required. `setup.ps1 -InstallMissing` installs `Gyan.FFmpeg.Shared` through Winget. If Winget is unavailable, use the manual fallback script or set `FFMPEG_PATH` to an existing installation. LibreOffice and Poppler are fallback installs; they are not needed when the supported PowerPoint renderer is available. On macOS, the first PowerPoint export may require allowing the application running the GUI to control Microsoft PowerPoint under **System Settings → Privacy & Security → Automation**.

---

### What is the recommended Windows install and uninstall flow?

For a ZIP release, double-click `install.bat`. It unblocks local scripts, runs setup with a process-scoped PowerShell bypass, creates or updates the desktop shortcut, and asks whether to start the GUI. The normal shortcut hides the backend; use `debug.bat` for visible output. To remove the local installation, use `uninstall.bat`; it preserves product resources and shared tools. Use `-RemoveInstallationDirectory` only with the explicit `DELETE` confirmation.

The **primary language is always English** (`en-US` or `en-GB`). This is enforced by validation:

```python
if config.primary_language.lower() not in {"en", "en-us", "en-gb"}:
    errors.append("primary_language must be English")
```

The **secondary language** is configurable to any Azure Speech locale with a Neural voice, for example `zh-CN`, `ja-JP`, `ko-KR`, `de-DE`, `fr-FR`, `es-ES`. Only **one secondary language** is supported per run.

To produce a video in a third language, run the pipeline again with a different `secondary_language` configuration.

---

### Can it run on Linux or macOS?

The CLI and most of the pipeline work on Linux and macOS. Limitations apply:

| Feature | Linux / macOS |
|---|---|
| CLI (`launchframe scan/inspect/build`) | ✅ Fully supported |
| Web GUI | ✅ Supported |
| PowerPoint rendering | ✅ Windows COM or macOS PowerPoint automation; LibreOffice remains the fallback |
| DOCX/PPTX/XLSX Vision rendering via Office | ✅ Uses Word/Excel/PowerPoint automation when available; LibreOffice remains the fallback |
| Windows `Select folder` dialog | ❌ Not available; type the path manually |
| `setup.ps1` / `run.ps1` | ❌ PowerShell scripts; use equivalent shell commands |

Set `VIDEO_RENDERER=libreoffice` on Linux/macOS to force the LibreOffice + Poppler path. On macOS, native PowerPoint, Word, and Excel conversion requires Automation permission; the pipeline falls back to LibreOffice when native Office automation is unavailable.

---

### Does the pipeline need internet access during generation?

| Stage | Internet required |
|---|---|
| Resource scan, config load | No |
| Vision analysis | Yes — LLM Vision API call |
| Draft generation | Yes — LLM API call |
| PPT build, PDF render | No |
| Audio synthesis | Yes — Azure Speech TTS API |
| Subtitle generation | No |
| Video rendering | No |
| Publishing | Never — manual upload only |

DIAL additionally requires **provider network access** for all API calls.

---

## 3. Duration control

### How do I control the video length?

Set `target_duration_seconds` in the Web GUI configuration panel or in `video-project.json`:

```json
{
  "output": {
    "target_duration_seconds": 300
  }
}
```

The minimum accepted value is **30 seconds**. Leave it blank to use the natural narration duration.

The LLM receives the target as an instruction when generating the Draft:

> *"The requested target duration is 300 seconds. Plan enough substantive narration and outline content to approach that duration at a natural speaking rate; do not slow the speech artificially."*

After audio synthesis, the pipeline checks whether the actual narration duration is within 20 % (or 10 seconds, whichever is larger) of the target. If it is within range, FFmpeg `atempo` is applied to fit exactly. If it is outside the tolerance, the build continues — the user has already been warned at draft approval time and chosen to proceed.

---

### What if the duration estimate is below target?

The estimated narration duration (computed from draft text before audio generation) is more than 20 % below the target. This is a heads-up, not a blocker — the build will proceed once you approve the draft.

Typical causes and fixes:

| Cause | Fix |
|---|---|
| Too little narration text for the target | Edit the Draft to add more detail per slide; or increase slide count |
| Too much narration text for the target | Edit the Draft to shorten each slide's narration; or increase the target |
| Target is unrealistically short for the content | Increase `target_duration_seconds` or remove slides from the outline |

When you click **Approve draft**, a confirmation dialog shows the estimate so you can decide whether to proceed or revise first.

---

### How much text produces how much audio?

Approximate reference at Azure Neural TTS natural speaking rates:

| Language | Rate | Text for 5 minutes |
|---|---|---|
| English (`en-US`) | ~150 words / min | ~750 words |
| Mandarin Chinese (`zh-CN`) | ~250 characters / min | ~1 250 characters |
| Japanese (`ja-JP`) | ~400 characters / min | ~2 000 characters |
| German (`de-DE`) | ~130 words / min | ~650 words |

These are approximate; actual duration depends on the chosen voice and SSML prosody settings.

---

### What does `gap_seconds` do?

`gap_seconds` (default `0.5`) adds a silence pad between each slide's narration when the dual-track WAV is assembled. For a 10-slide video, the default adds 5 seconds. Increase it to give viewers more time between slides:

```json
{ "output": { "gap_seconds": 1.0 } }
```

Valid range: `0` to `10` seconds.

---

## 4. Content quality

### Can I customize the Draft and PPT prompts?

Yes. The Draft section provides a **Customize the draft prompt** editor with **Load saved prompt** and **Save prompt** controls. The current Draft prompt is used immediately when generating, even if it has not been saved. If you edit it, the UI marks it as changed; loading the saved version over unsaved text opens the themed confirmation dialog.

The Stage build and review section provides a separate **Customize the PPT generation prompt** editor directly above **Build PPT**. It has its own load/save controls and must be saved before building if it has been modified. The two prompts are stored independently in the project settings as `draft_instructions` and `presentation_instructions`.

### The LLM draft quality is poor. How do I improve it?

The draft quality is directly proportional to the richness of the input material. In order of impact:

1. **Add more structured text**: Markdown files with clear headings and bullet points give the LLM the best signal. PDFs and DOCX documents are also extracted.
2. **Provide an existing PPTX**: slide titles, body text, and speaker notes are extracted and prepended to the LLM prompt — this is the strongest single signal for narration alignment.
3. **Add co-located subtitles for reference videos**: if a demo `.mp4` has a `.srt` or `.vtt` alongside it, the transcript is included in the LLM prompt.
4. **Enable Vision**: analyzed image descriptions supplement the text prompt, especially for diagram-heavy products.
5. **Edit the Draft directly**: the Draft is fully editable before approval. Adjust the outline, rewrite narration paragraphs, and add or remove slides before approving.

---

### Vision analysis results are wrong or inconsistent. What can I do?

- **Edit before approving**: the Vision review panel lets you modify any field in `vision-analysis.json` before approving. Correct descriptions, `suggested_slide` assignments, and `key_points` directly.
- **Disable Vision**: if the image content is already captured in text form, Vision adds little value and its inaccuracies could mislead the LLM. Uncheck *Enable Vision image analysis* and save.
- **Adjust the model**: a more capable Vision model (e.g. `gpt-4.1` vs `gpt-4o-mini`) generally produces better results for complex diagrams. Change the model in the configuration and re-analyze.
- **Reduce image noise**: screenshots with lots of UI chrome or code text can confuse Vision. Crop or annotate images before including them.

---

### The narration does not match the slide content.

This happens when the LLM generates narration from text documents alone, without seeing the actual slide content.

Fix:
- Supply the source PPTX in the resource directory. Its slide text and notes are extracted and included in the LLM prompt.
- After Draft generation, review the outline — each `slide` number in `outline` must correspond to a slide in the PPTX. Edit `primary_narration` and `secondary_narration` entries to align with the actual slide content.

---

### How are multiple PPTX files distinguished?

The GUI separates existing source presentations from slide templates. Select one or more PPTX files as source material: a single selected PPT is reused as the source deck, while multiple selected PPTs are combined as LLM reference material and produce a new `outputs/presentation.pptx`. Files under `templates/` or named `*.template.pptx` are template candidates. The GUI does not silently choose the first PPT when multiple source files are available.

The LLM decides the number of slides based on the source material and the target duration. There is no hard limit. Practical guidance:

- At a natural speaking pace (~1–2 minutes per slide), a 5-minute video typically has 4–8 slides.
- The outline is fully editable before approval. Add, remove, or reorder slides in the Draft before approving.
- If an existing PPTX is used, the slide count is fixed by that deck. The LLM generates narration for each existing slide.

---

## 5. Security and credentials

### Where is the Azure Speech key stored?

The Speech key is obtained at runtime from the Azure ARM API using `DefaultAzureCredential` and kept **in memory only**. It is never written to any file, never logged, and never committed to Git. Subscription ID is masked in the Web GUI.

---

### Where are DIAL and ELITEA tokens stored?

Tokens are stored in **Windows Credential Manager** (via `keyring`). They are never written to:

- `video-project.json` or any project file
- Browser `localStorage`
- Git history
- Application logs

If `keyring` is unavailable, the token must be re-entered each session.

---

### Does generating a video send product content to external services?

Yes, in two stages:

| Stage | Data sent | Destination |
|---|---|---|
| Vision analysis | Image bytes (base64) | LLM Vision API (CodeMie / DIAL / ELITEA) |
| Draft generation | Extracted text from all content files, PPTX, subtitles, vision results | LLM API (CodeMie / DIAL / ELITEA) |
| Audio synthesis | Narration text (SSML) | Azure Speech TTS API |

Video rendering, subtitle generation, and all review stages are **fully local** with no external API calls.

Before using this tool with confidential product materials, verify that the selected LLM Provider and Azure Speech region comply with your organization's data handling policies.

---

### What should not be placed in the product resource directory?

- API keys, passwords, or tokens
- Personal data (PII)
- Classified or legally privileged documents

The access boundary prevents path traversal outside the selected directory, but the LLM will read and process every supported file it finds.

---

## 6. Pipeline and approvals

### Can I skip any stage?

| Stage | Skippable? | How |
|---|---|---|
| Vision analysis | ✅ Yes | Uncheck *Enable Vision image analysis* and save config |
| Draft approval | ❌ No | Required before PPT build; can be bypassed in CI with `VIDEO_MCP_APPROVE_DRAFT=1` |
| PPT / PDF review | ✅ GUI flow continues after review | The GUI accepts the reviewed presentation when starting audio; standalone pipeline callers can require approval or use `VIDEO_MCP_APPROVE_PRESENTATION=1` |
| Audio generation | ✅ Automatic acceptance | Generated audio is available for local review; no approval gate |
| Subtitle generation | ✅ Automatic acceptance | Generated subtitles are available for local review; no approval gate |
| Video review | ✅ Yes | No approval gate; review is informal |

The `VIDEO_MCP_APPROVE_*` environment variables are intended for automated CI pipelines, not for bypassing human review in production runs.

---

### Can I generate only the PPT without the video?

Yes. Edit/save the PPT prompt if needed, click **Build PPT**, and stop there. The PPTX and PDF are written to the project work/output directories for review. Audio, subtitles, and video are not generated until **Build audio + subtitles** is clicked; the GUI accepts the reviewed presentation when that stage starts.

Via CLI:
```powershell
launchframe build D:\projects\my-product  # full run
```
The CLI always runs to completion; partial stops require the `stop_after` parameter in direct API calls.

---

### I approved a stage but want to regenerate it. Is that possible?

Yes. In the Web GUI, click the **Regenerate** link for any completed stage. This clears that stage's output files and all downstream explicit approvals, allowing a fresh build from that point onward.

Stages that can be individually regenerated: Draft, PPT, audio + subtitles, video.

---

### Does switching the resource directory preserve my approvals?

No. Switching directories **resets all run state** for the previous directory: active builds are cancelled, Pi is stopped, all explicit approvals and output references are cleared from the UI. The approval files (`.video-work/approvals.json`) remain on disk in the old directory and will be restored if you switch back to it.

Azure authentication and Provider tokens are preserved across directory switches.

---

### Can I run the pipeline on the same directory multiple times?

Yes. The pipeline uses existing files as a cache:

- If `content-draft.json` exists and is approved, Draft generation is skipped.
- If the PPTX exists and is approved, PPT generation is skipped; the GUI also exposes the current PPT/PDF for review before starting audio.
- If audio files exist, audio synthesis is skipped.

To force regeneration, click **Regenerate** for the desired stage in the Web GUI, or delete the relevant files from `.video-work/`.

---

## 7. Output formats

### Where are the output files?

```text
<resource-directory>/
├── .video-work/                     intermediate files and approvals
│   ├── vision-pages/                rendered PNG frames (PDF, PPTX, video keyframes)
│   ├── vision-analysis.json
│   ├── content-draft.json
│   ├── narration-primary.json
│   ├── narration-secondary.json
│   ├── audio-primary/slide-*.wav
│   ├── audio-secondary/slide-*.wav
│   ├── primary.wav
│   ├── secondary.wav
│   ├── review-primary.wav
│   ├── review-secondary.wav
│   └── approvals.json
└── outputs/
    ├── presentation.pptx
    ├── presentation.pdf
    ├── presentation-primary.srt
    ├── presentation-primary.vtt
    ├── presentation-secondary.srt
    ├── presentation-secondary.vtt
    ├── presentation-bilingual.srt
    ├── presentation-bilingual.vtt
    ├── presentation-primary.mp4
    ├── presentation-secondary.mp4
    └── presentation-dual.mp4
```

---

### Can I customize the PPTX template or slide style?

Not directly in the current release. The generated PPTX uses a built-in dark-blue theme (title slide + content slides with bullet points and optional images).

To use a custom design:

1. Create a PPTX with your template and at least the correct number of slides.
2. Place it in the resource directory as the source deck.
3. The pipeline will use it as-is for audio, subtitles, and video generation, skipping the generation stage.

Richer template support and branding options are planned for a future release.

---

### What subtitle formats are produced?

Three tracks, two formats each:

| File | Content |
|---|---|
| `presentation-primary.srt/.vtt` | Primary language (English) only |
| `presentation-secondary.srt/.vtt` | Secondary language only |
| `presentation-bilingual.srt/.vtt` | Both languages, interleaved by cue |

Subtitles are generated from Azure Speech word-boundary events and are time-aligned with the review audio (after atempo normalization if a target duration is set).

---

### What video codec and container are used?

FFmpeg default settings: **H.264 video** (`libx264`) in an **MP4 container**, with **AAC audio**. The three output videos are:

| File | Audio track |
|---|---|
| `presentation-primary.mp4` | Primary language narration only |
| `presentation-secondary.mp4` | Secondary language narration only |
| `presentation-dual.mp4` | Both languages interleaved (EN narration + silence pad, then ZH narration + silence pad, per slide) |

Resolution is determined by the PPTX slide dimensions; default PowerPoint widescreen is 1920 × 1080.
