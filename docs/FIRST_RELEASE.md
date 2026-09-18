# LaunchFrame — v1 User Workflow

This document describes the usable first release of LaunchFrame, the standalone Windows Web GUI for product promotional videos.

## Current v1 pipeline

```text
Select product resource directory
  → automatic resource scan
  → Pi starts automatically
  → Azure authentication and Subscription selection
  → Speech Resource and Voice catalog
  → Provider authentication and model selection
  → optional Vision analysis and approval
  → LLM Draft prompt, generation, editing, and approval
  → PPT prompt, PPTX + PDF generation, and review
  → Azure Speech audio + subtitles generated and automatically accepted
  → language videos and dual-track video
  → local video review and delivery
```

## Start the Web GUI

### Complete first installation

Extract the Source ZIP or clone the repository, then double-click:

```text
install.bat
```

`install.bat` is the normal one-step Windows installer. It unblocks scripts, automatically installs missing Python and FFmpeg through Winget (`Gyan.FFmpeg.Shared`), creates the virtual environment and desktop shortcut, and asks whether to start the Web GUI. No separate `setup.ps1`, `run.ps1`, or `unblock-scripts.bat` command is required for a normal first installation.

The normal shortcut hides the backend console; use `debug.bat` for visible backend output. The Web GUI provides the red Exit button and Backend service status inside `Progress details`.

To uninstall the local application, double-click `uninstall.bat`. It stops the service, removes the shortcut and installer-created local environment, and preserves product resources, generated outputs, and shared tools. Use `scripts\uninstall.ps1 -RemoveInstallationDirectory` only when you explicitly want to remove the entire installation folder.

After accepting the start prompt, the installer starts the local Web GUI. The GUI is localhost-only by default.

## Rendering prerequisites

The project searches for FFmpeg in this order:

1. `FFMPEG_PATH`;
2. `ffmpeg.exe` on `PATH`;
3. `<project>/.tools/ffmpeg/ffmpeg.exe`;
4. `launchframe/.tools/ffmpeg/ffmpeg.exe`.

FFmpeg is not included in the source repository, and Git LFS is not required. The normal `install.bat` flow installs `Gyan.FFmpeg.Shared` through Winget. If Winget is unavailable, use the manual fallback script or set `FFMPEG_PATH` to an existing installation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\install-ffmpeg.ps1
```

The fallback script downloads a public FFmpeg build and verifies its SHA256 checksum. The normal installer uses Winget instead.

Microsoft Office is preferred on Windows: Word COM converts DOCX to PDF and PowerPoint COM handles PPTX rendering. On macOS, installed PowerPoint is used through Automation for PPTX-to-PDF rendering and PyMuPDF renders the resulting PDF pages. LibreOffice remains the fallback. Set `VIDEO_RENDERER=libreoffice` to force the fallback renderer.

## GUI workflow

### 1. Product resources

The first section selects one Product resource directory. The selected directory immediately becomes the access boundary for the run; a separate workspace root is not required. On a first installation, the GUI defaults to `examples/mock-product` when that example exists. Click `Select resource folder` to choose another folder containing product documents, images, tables, PDF/DOCX files, or a presentation. The GUI automatically sets the boundary, scans resources, and starts Pi for the selected directory. `video-project.json` is optional; when it is absent, settings are stored in the application-managed `.video-work/project-sessions/` area. A first-time floating guided tour is available from `Guide tour`; it highlights controls one at a time and can be closed and reopened manually.

If the resource directory contains one or more PPTX files, select one or more in **Source PPT presentations**. A single selected PPT is parsed and reused without being overwritten. Multiple selected PPTs are combined as LLM reference material and produce a new `outputs/presentation.pptx`. Files under `templates/` (or named `*.template.pptx`) are template candidates shown separately in **PPT slide template**.

### 2. Configure Azure

The GUI checks Azure login status and loads Subscriptions after authentication. The sequence is:

```text
Login Azure
  → Azure Subscription
  → Discover Speech resources
  → Speech Resource
  → Load Voice catalog
```

The Speech key is retrieved through the vendored `azure-mcp` integration and kept in memory only.

### 4. Configure language, Voice, duration, and LLM/Vision

English is always the primary language. The secondary language is selected from the Azure Voice catalog and defaults to `zh-CN`.

The provider and model controls are in the same section:

```text
Login CodeMie SSO / Logout CodeMie
Model provider: CodeMie Web / Platform or CodeMie CLI
CodeMie model (applied automatically when selected)
Model details
Provider usage and quota
Enable Vision image analysis
Check and save configuration
```

`Model details` loads the live multi-model catalog, including provider channel, pricing, input type, Vision/Reasoning/Tools capabilities, context window, and max output. The active model is highlighted. `Refresh usage` loads the current provider usage/quota information. DIAL requires the company VPN and a valid token entered in the GUI. ELITEA requires a valid token. Tokens are kept in the local Pi process environment only and are not written to project files.

Pi is an internal background service. It starts automatically when a product resource directory is loaded. Pi status is shown in the header of the Product resources section. No manual Pi start or stop is required.

The selected model is saved only after `Check and save configuration` succeeds. Vision is available only for a model whose input capabilities include images. If Vision is enabled, Vision approval is mandatory; `require_review` is not a user-controlled bypass.

Target duration is optional. Leave it blank to use the natural audio duration. The GUI displays the measured actual duration after audio generation. If a configured target differs from natural narration by more than 20% or 10 seconds, the GUI asks for more narration content instead of approving the audio.

### 5. Vision and Draft review

> Steps 3 and 4 can be done in either order. Azure and Provider setup are independent.

When images or PDF/DOCX resources exist, a Vision-capable model is selected, and Vision is enabled:


```text
Analyze images
  → .video-work/vision-analysis.json
  → Approve Vision
```

The Vision result contains OCR, descriptions, key points, Alt Text, confidence, source file, document page (for PDF/DOCX), and `suggested_slide`. On Windows, DOCX files are converted through Microsoft Word COM and PDF/DOCX pages are rendered with PyMuPDF before Vision analysis. LibreOffice remains a fallback. The Web GUI displays editable Vision cards. Re-running Vision analysis clears Vision and all downstream approvals.

After Vision review and approval, optionally edit the Draft prompt in the same section. **Load saved prompt** restores the previous value, changes enable **Save prompt**, and loading over unsaved changes uses the themed confirmation dialog. The current text is used immediately by `Generate LLM draft`; saving is only needed to reuse it later.

Click `Generate LLM draft`. Pi sends the request to the selected Provider/model. The model writes:

```text
.video-work/content-draft.json
.video-work/narration-primary.json
.video-work/narration-secondary.json
```

Use the Draft editor as follows:

```text
Load draft
  → edit JSON if needed
  → Save draft
  → Approve draft
```

`Save draft` becomes active only after edits. Saving invalidates Draft, PPT, audio, subtitle, and video outputs because downstream outputs must be regenerated.

### 6. Build and approve the PPT

The Stage build and review section places the PPT prompt directly above the build button:

```text
Load saved prompt  |  Save PPT prompt
Build PPT
```

Edit the PPT prompt to provide presentation-generation guidance. Modified text is marked as unsaved, and the themed confirmation dialog is used if a saved prompt is loaded over it. The prompt must be saved before building. After PPT exists, the same button becomes `Regenerate PPT`.

`Build PPT` uses the approved Draft and Vision result. It creates:

```text
outputs/presentation.pptx
outputs/presentation.pdf
```

The PPTX download link and embedded PDF preview are shown directly below the PPT row. Review the generated artifacts there. When the GUI starts the audio stage, it automatically accepts the reviewed presentation; standalone pipeline callers can still require explicit presentation approval.

### 7. Build and review audio/subtitles

The second build row is:

```text
Build audio + subtitles  |  Review audio/subtitles
```

Audio and subtitles are automatically accepted after generation; no separate approval action is required. After audio exists, the same button becomes `Regenerate audio + subtitles`.

Audio generation uses Azure Speech and records word boundaries and sentence timings. It creates:

```text
.video-work/audio-primary/
.video-work/audio-secondary/
.video-work/primary.wav
.video-work/secondary.wav
.video-work/primary-manifest.json
.video-work/secondary-manifest.json
```

The GUI provides:

- Editable WebVTT subtitle cues; manual subtitle edits update both WebVTT and SRT;
- Primary-language audio player;
- Secondary-language audio player;
- Seekable playback;
- Live synchronized subtitles;
- SRT and WebVTT review links.

Manual subtitle edits only change captions and timing; they do not change generated audio. To change spoken text or translation, edit and save the Draft, approve it, and regenerate audio + subtitles. The browser review audio is normalized with FFmpeg only when a target duration is configured. A longer target is handled by silence padding, not by slowing speech. With no target, natural audio duration is used.

### 8. Build and review videos

The third row is:

```text
Build video
```

After video exists, the same button becomes `Regenerate video`; review the local videos and regenerate them if needed.

Outputs are:

```text
outputs/presentation-primary.mp4
outputs/presentation-secondary.mp4
outputs/presentation-dual.mp4
```

The video review area contains large players for all three videos. Each player has controls and WebVTT subtitles. The dual-track player provides an audio-track selector:

```text
Embedded dual-track audio
English audio
Secondary-language audio
```

The language-specific fallback is used because Chrome, Edge, and Firefox do not consistently expose native MP4 multi-track selection.

### 9. Progress details and local delivery

Step 7 is `Progress details and local delivery`. `Refresh status` reads both workflow state and actual output files. If a previous process left a stale `video_rendering/running` state but all MP4 files exist, the GUI reconciles the state to `video_ready/completed`.

The project completes when the videos are generated. Review them locally and regenerate if needed; no separate video approval is required. Download the reviewed PPTX, PDF, audio, subtitles, and MP4 files, then upload them to the destination website using the organization's normal publishing process.

To cancel any running build, click the active (pulsing) button a second time. A confirmation dialog will appear; click **Terminate** to stop the current stage, or **Continue** to keep it running.

## Troubleshooting

### Windows blocks setup.ps1 or run.ps1

If FFmpeg is missing, run `tools/install-ffmpeg.ps1` from the project directory to download it separately. The script downloads a public build and verifies its SHA256 checksum; a Windows tools ZIP and Git LFS are not required.

If the scripts are already extracted, run:

```text
unblock-scripts.bat
```

This handles common `RemoteSigned` download blocks for `.ps1` and `.bat` files. If the company policy is `AllSigned`, AppLocker, or WDAC, unblocking is not sufficient; the scripts must be signed with the company Code Signing Certificate or approved by IT Security.

### Web GUI ports are occupied

Run:

```powershell
.\\stop.ps1
.\\run.ps1
```

`run.ps1` automatically selects another pair of localhost ports if the default ports are occupied.

## Generated files

```text
.video-work/
├── content-draft.json
├── vision-analysis.json
├── narration-primary.json
├── narration-secondary.json
├── primary-manifest.json
├── secondary-manifest.json
├── primary.wav
├── secondary.wav
├── review-primary.wav
├── review-secondary.wav
└── approvals.json

outputs/
├── presentation.pptx
├── presentation.pdf
├── presentation-primary.srt
├── presentation-secondary.srt
├── presentation-bilingual.srt
├── presentation-primary.vtt
├── presentation-secondary.vtt
├── presentation-bilingual.vtt
├── presentation-primary.mp4
├── presentation-secondary.mp4
└── presentation-dual.mp4
```

Large generated media and runtime tools are excluded from Git. FFmpeg is not tracked in the repository; users download it separately into the Git-ignored `.tools/ffmpeg/` directory during setup.
