# LaunchFrame

A review-gated workspace for creating multilingual product promotional videos from product resources.

It reads text, images, documents, tables, videos, and an optional existing PPTX from a product resource directory. It extracts content from every supported format — including PPTX slide text, video keyframes, and co-located subtitles — and passes it through Vision analysis and LLM drafting before generating narration, PDF/video outputs, and synchronized subtitles. All reviewed deliverables are kept on the local machine for the user to upload and publish.

- v1 English user workflow: [docs/FIRST_RELEASE.md](docs/FIRST_RELEASE.md)
- v1 Chinese user workflow: [docs/FIRST_RELEASE.zh-CN.md](docs/FIRST_RELEASE.zh-CN.md)
- Complete pipeline diagram: [docs/pipeline.md](docs/pipeline.md)
- Chinese detailed workflow: [VIDEO_GENERATION_WORKFLOW.zh-CN.md](VIDEO_GENERATION_WORKFLOW.zh-CN.md)
- English detailed workflow: [VIDEO_GENERATION_WORKFLOW.md](VIDEO_GENERATION_WORKFLOW.md)
- Resource layout: [docs/RESOURCE_LAYOUT.md](docs/RESOURCE_LAYOUT.md)
- Example project: `examples/product-video/`

## macOS and Linux

The Web GUI and the core pipeline can also run on macOS and Linux. Windows uses Office COM when available. On macOS, installed PowerPoint, Word, and Excel can be detected and used through macOS automation for Office-to-PDF rendering; otherwise the pipeline uses LibreOffice plus Poppler. FFmpeg is required for video output.

### Install

```bash
./setup.sh --install-missing
```

The installer creates `.venv`, installs the Python package, checks Node.js, Git, Azure CLI, Pi, FFmpeg, and the available presentation renderer, and reports anything that must be installed manually. On macOS it uses Homebrew. On Debian/Ubuntu it uses `apt-get` when `--install-missing` is supplied. Install Azure CLI separately when it is not available from the system package manager.

### Start

```bash
./run.sh --no-browser
```

Use `./run.sh --replace` to replace an existing Web GUI process. The script writes `.video-work/web-gui-runtime.json`, keeps logs under `.video-work/`, chooses alternate ports when necessary, and opens the browser with `open` on macOS or `xdg-open` on Linux unless `--no-browser` is used.

Set `VIDEO_RENDERER=libreoffice` to force the cross-platform renderer. The default `auto` renderer already selects LibreOffice when Microsoft PowerPoint is unavailable.

The legacy `setup.ps1`, `run.ps1`, `install.bat`, and optional Tk desktop GUI remain available for Windows. The browser-based Web GUI is the recommended interface on all platforms.

## Design goals

- Product resources are supplied through a separate directory and automatically categorized by extension and filename convention.
- The first stage creates the PPTX from text, documents, tables, and optional images when no existing deck is provided.
- English is always the primary language.
- The secondary language is configurable from the Azure Speech Voice catalog and defaults to Simplified Chinese (`zh-CN`).
- The target video duration is configurable in `output.target_duration_seconds`.
- The mandatory LLM stage analyzes product materials, generates an outline, and drafts both language narrations for human review.
- Multiple existing PPTX files can be selected as LLM reference material; a single selected PPTX is reused as the source deck, while generated decks are written to `outputs/presentation.pptx`.
- PPTX files under `templates/` or named `*.template.pptx` are treated as slide-template candidates.
- The second stage creates video from the generated or supplied PPTX.
- The generation service does not depend on the original product repository or Pi.
- MCP clients can inspect resources and start a build through stdio.
- Project paths are constrained by `VIDEO_PROJECT_ROOT`.
- Credentials stay in environment variables and are never stored in product assets.
- Speech timing metadata is retained for accurate subtitle generation.
- The project ends with locally reviewed deliverables; users upload and publish them through their normal website workflow.

```
📁 Product resources          Stage 0 · Scan
   .md / .txt / .pdf ──────► categorize by type
   .csv / .xlsx       ─┐
   .png / .jpg ────────┤
   existing PPTX ──────┤  → slide text extracted for LLM
   .mp4 / .mov ────────┤  → keyframes extracted for Vision
   .srt / .vtt ────────┘  → transcript text extracted for LLM
          │
          ▼
   Stage 1 · Vision (optional)                                👤 Approve Vision
   images + PPTX slides + video keyframes                   │
   + PDF/DOCX pages → Pi Vision LLM  ───────────────────────┐
   → vision-analysis.json                                   │
          │                                                 │
          ▼                                                 │
   Stage 2 · LLM Draft                                      │ 👤  Approve Draft
   content + tables + PPTX text + video transcripts         │
   + vision results  ──────────────────────────────────┐    │
   → Pi LLM (CodeMie / DIAL / ELITEA)                  │    │
   → content-draft.json                                │    │
     outline · EN narration · ZH narration             │    │
          │                                            │    │
          ▼                                            ▼    ▼
   Stage 3 · Build PPT                                        👤 Review PPT/PDF
   outline → python-pptx → .pptx
   → PowerPoint COM / LibreOffice → presentation.pdf
          │
          ▼
   Stage 4 · Build Audio + Subtitles
   narration → Azure Neural TTS → per-slide WAV
   → merged dual-track WAV (EN+ZH interleaved)
   → word boundaries → SRT / WebVTT (primary · secondary · bilingual)
   → automatically accepted for local review
          │
          ▼
   Stage 5 · Build Video
   PPTX slides + WAV + VTT → FFmpeg
   → presentation-primary.mp4
   → presentation-secondary.mp4
   → presentation-dual.mp4
          │
          ▼
   Stage 6 · Local Review & Delivery
   👤 review locally → download → 📤 upload manually
```

Vision and Draft are explicit review gates. The GUI places independent Draft and PPT prompt editors next to their stages; prompts can be loaded, saved, and are checked for unsaved changes before the relevant action. Audio and subtitles are automatically accepted after generation and remain available for local review. PPT/PDF is reviewed in the GUI and accepted automatically when the GUI starts the audio stage. Video is reviewed locally; publishing is intentionally outside this project.

## Install on Windows

Open PowerShell in the standalone project directory:

```powershell
cd D:\path\to\launchframe
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

For the complete first Windows installation, double-click `install.bat`:

```text
install.bat
```

It unblocks the local scripts, runs setup with the required PowerShell bypass, creates or updates a desktop shortcut, and asks whether to start the Web GUI immediately. The normal shortcut starts the backend in hidden mode. Use `debug.bat` when you need to see the backend console.

`install.bat` automatically unblocks scripts, installs missing Python and FFmpeg through Winget (`Gyan.FFmpeg.Shared`), creates `.venv`, installs project dependencies, creates the desktop shortcut, and offers to start the Web GUI. For normal first-time installation, no separate `unblock-scripts.bat`, `setup.ps1`, or `run.ps1` command is required.

For an already configured installation, run:

```powershell
.\setup.ps1
.\run.ps1
```

If Windows marks downloaded scripts as blocked, run this first:

```text
unblock-scripts.bat
```

This removes the downloaded-file mark from local `.ps1`/`.bat` files. It is sufficient for common `RemoteSigned` policies. If PowerShell reports **"running scripts is disabled on this system"**, run setup with a process-scoped bypass instead of changing the machine policy:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -InstallMissing
```

If `Get-ExecutionPolicy -List` shows an enforced `MachinePolicy` or `UserPolicy`, the bypass may be blocked by company policy; contact IT Security or use an approved signed script. Company `AllSigned`/AppLocker policies also require a company code-signing certificate.

To remove the local application installation, double-click `uninstall.bat`. It stops a running instance, removes the desktop shortcut and installer-created `.venv`/local FFmpeg, and preserves product resources, generated outputs, and shared tools. Use `scripts\uninstall.ps1 -Purge` for additional local cleanup, or use `-RemoveInstallationDirectory` only after the explicit `DELETE` confirmation.

FFmpeg is deliberately **not stored in the Git repository** and Git LFS is not required. The recommended `install.bat` command installs it through Winget using `Gyan.FFmpeg.Shared`. If Winget is unavailable, install FFmpeg manually or set `FFMPEG_PATH` to an existing installation:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\tools\install-ffmpeg.ps1
```

The fallback script downloads a public FFmpeg build, verifies its SHA256 checksum, and installs it under the Git-ignored `.tools\ffmpeg\` directory. The normal installer uses Winget instead.

Other external rendering tools:

- LibreOffice Impress (`soffice.exe`) as the cross-platform fallback;
- Poppler for Windows (`pdftoppm.exe`) as the cross-platform fallback;

If Microsoft PowerPoint Desktop is installed, Windows uses PowerPoint COM automatically in `VIDEO_RENDERER=auto` mode. If Microsoft PowerPoint for Mac is installed, macOS uses its automation interface for PDF export and PyMuPDF for slide frames. Force a renderer with:

```powershell
$env:VIDEO_RENDERER = "powerpoint"
# or
$env:VIDEO_RENDERER = "libreoffice"
```

Set an optional FFmpeg path if FFmpeg is not on `PATH`:

```powershell
$env:FFMPEG_PATH = "C:\tools\ffmpeg\bin\ffmpeg.exe"
```

The Web GUI sets `VIDEO_PROJECT_ROOT` automatically when a product resource directory is selected. For CLI use, set it explicitly:

```powershell
$env:VIDEO_PROJECT_ROOT = "D:\video-projects"
```

The project includes the `azure-mcp` source under `vendor/azure-mcp/`, uses its MCP tools for Azure identity and resource discovery, then obtains the Speech key in memory for the TTS voice-list request. Configure `azure.speech_resource_id` only when multiple resources exist. Azure credentials are supplied through `DefaultAzureCredential` in the bundled azure-mcp process; `az login` is one supported local credential source:

```powershell
az login
az account set --subscription "<subscription-id>"
```

Run the CLI without Pi:

```powershell
.\.venv\Scripts\launchframe.exe scan D:\video-projects\my-product
.\.venv\Scripts\launchframe.exe inspect D:\video-projects\my-product
.\.venv\Scripts\launchframe.exe build D:\video-projects\my-product
```

After review, upload the generated local files to the destination website using the organization's normal publishing process.

## Install on Linux/macOS

```bash
python3 -m venv .venv
./.venv/bin/pip install -e .
```

Set the environment variables, log in to Azure, and run:

```bash
export VIDEO_PROJECT_ROOT=/path/to/product-projects
az login
az account set --subscription "<subscription-id>"
./.venv/bin/launchframe scan /path/to/product-projects/my-product
./.venv/bin/launchframe inspect /path/to/product-projects/my-product
./.venv/bin/launchframe build /path/to/product-projects/my-product
```

## Pi integration

The project includes a Pi Package manifest and a project-local settings file:

```text
.pi/settings.json
```

It declares:

```text
npm:pi-codemie@1.0.24
```

Pi automatically installs the npm extension after the project is trusted. In the Web GUI, Pi starts automatically when a product resource directory is selected; CodeMie login and model selection are done through the GUI. For direct Pi CLI use:

```text
/login codemie
/model
```

The project extension provides these workflow commands:

```text
/video-scan
/video-inspect
/video-draft
/video-build
/video-model-help
```

The commands call the local `launchframe` CLI and retain the deterministic build pipeline. `/video-draft` asks the selected CodeMie model to write a reviewable draft under `.video-work/`; `/video-build` uses that approved draft. Pi is used for SSO, model selection, interaction, and LLM/Vision orchestration; it is not required for direct CLI or MCP use. Publishing is intentionally outside this project.

## Local GUI

Start the Windows GUI:

```powershell
.\.venv\Scripts\launchframe-gui.exe
```

The GUI provides product directory selection, automatic resource scanning, Azure login/Subscription/Speech Resource/Voice selection, CodeMie SSO, model selection, independent Draft and PPT prompt editors with load/save controls, Vision analysis, Draft editing, PPT/PDF/audio/subtitle/video review, and Vision/Draft/PPT approvals. Pi runs as an internal background service and is started automatically when needed. `Progress details` shows backend status and logs; the red `Exit` button stops the local service and Pi. Use `debug.bat` when the backend console should remain visible. It generates deliverables locally; publishing is intentionally outside this project.

For the browser-based local GUI:

```powershell
.\.venv\Scripts\launchframe-web.exe `
  --host 127.0.0.1 `
  --port 8875 `
  --websocket-port 8876
```

Open `http://127.0.0.1:8875/`. The Web GUI binds to localhost by default. It separates `Build PPT`, `Build audio + subtitles`, and `Build video`, requires approval for Draft, Vision, and PPT, and provides PPT/PDF review before audio generation. Audio and subtitles are automatically accepted after generation and can be reviewed locally. Video is locally reviewed after generation and does not require a separate approval stage.

## Installation troubleshooting

If Windows blocks downloaded scripts, right-click the downloaded ZIP, open **Properties**, select **Unblock**, click **Apply**, and extract it again. For already extracted files, run:

```text
unblock-scripts.bat
```

This handles common `RemoteSigned` policies. `AllSigned`, AppLocker, and WDAC policies still require a company code-signing certificate or IT Security approval. If the Web GUI ports are occupied, run `stop.ps1` and then `run.ps1`; the launcher automatically finds another localhost port pair.

## GitHub CI/CD

The project includes `.github-ci.yml` with these stages:

```text
validate → test → build → Pages → manual integration → manual Release
```

CI automatically runs Ruff, Python compilation, JSON validation, API tests, package building, and documentation Pages generation. The manual Windows integration job can run `setup.ps1` and provider checks on a Windows Runner.

CI does not call Azure Speech, LLM, Vision, or upload product videos automatically. The manual Release job creates a source/package Release only; users generate, review, and upload product media themselves.

## MCP server

Start the MCP server on Windows:

```powershell
.\.venv\Scripts\launchframe-mcp.exe
```

Start it on Linux/macOS:

```bash
./.venv/bin/launchframe-mcp
```

An MCP host such as Pi, Claude Desktop, or an internal MCP client can launch this executable over stdio. Pi is optional; the `launchframe` CLI is sufficient for direct execution.

## MCP tools

- `list_product_resources(project_dir)` — list files without reading file contents.
- `azure_login_status(project_dir)` — check Azure identity through azure-mcp.
- `discover_speech_resources(project_dir, subscription_id)` — list Speech resources through azure-mcp.
- `list_tts_voices(project_dir, resource_id)` — retrieve the supported Voice catalog without returning the key.
- `scan_product_resources(project_dir)` — automatically categorize discovered files.
- `inspect_video_project(project_dir)` — validate the selected resource directory and return the effective resource manifest; `video-project.json` is optional for GUI/resource-folder workflows.
- `analyze_product_images(project_dir)` — optional Vision LLM image analysis for review.
- `generate_content_draft_tool(project_dir)` — optional text LLM extraction, outline, and narration draft for review.
- `build_video_project(project_dir)` — generate PPTX, narration, subtitles, PDF, and language videos.
The LLM content stage is mandatory for the Web GUI workflow and always requires Draft approval before building. Build stages are intentionally separate so a team can review generated content and media locally before uploading it.

## Vision analysis

Vision is enabled by default when a Vision-capable model and Vision inputs are available. Vision always requires `Approve Vision`; `require_review` is not a user-controlled bypass. Vision supports images and rendered PDF/DOCX pages. The Vision stage writes `.video-work/vision-analysis.json`.

```json
{
  "vision_analysis": {
    "enabled": true,
    "provider": "openai-compatible",
    "model": "gpt-4.1",
    "base_url": "https://api.openai.com/v1",
    "max_image_bytes": 5000000
  }
}
```

In the Web GUI, Vision uses the selected authenticated CodeMie Vision model. Direct CLI/MCP execution can use `VIDEO_VISION_API_KEY`, `OPENAI_API_KEY`, or `AZURE_OPENAI_API_KEY`. The analysis is passed to the content stage so image facts can influence the outline without putting raw image bytes into the text prompt.

## LLM content stage

The Web GUI always uses the selected Provider/model for content analysis and Draft generation. Select one folder containing product resources; it immediately becomes the access boundary for the run. `video-project.json` is optional in the GUI, and settings are stored in the application-managed session. Configure the Provider and model in `video-project.json` when using the CLI:

```json
{
  "content_generation": {
    "enabled": true,
    "provider": "openai-compatible",
    "model": "gpt-4.1-mini",
    "base_url": "https://api.openai.com/v1",
    "require_review": true
  }
}
```

Set one API key:

```text
VIDEO_LLM_API_KEY
OPENAI_API_KEY
AZURE_OPENAI_API_KEY
```

For Azure OpenAI also set `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, and optionally `AZURE_OPENAI_API_VERSION`. The LLM returns a structured outline plus primary and secondary narration drafts. Human approval is required before the PPTX and video build continues.

## Resource-driven build

A product resource folder can contain:

```text
product-video/
├── video-project.json
├── content/
├── assets/
├── narration/
├── subtitles/
└── outputs/
```

See [docs/RESOURCE_LAYOUT.md](docs/RESOURCE_LAYOUT.md) for the contract and supported file types.
