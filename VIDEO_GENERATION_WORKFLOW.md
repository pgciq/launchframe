# LaunchFrame: Team Workflow

> **Standalone v1 status:** The currently usable Windows Web GUI workflow is documented in [docs/FIRST_RELEASE.md](docs/FIRST_RELEASE.md). The older Release/Pages sections below are historical architecture notes and are not active product functionality. It includes automatic background Pi startup, Provider/model selection, separate Draft/PPT prompt editors with load/save controls, Vision/Draft review, automatic acceptance of generated audio/subtitles, FFmpeg discovery, audio/subtitle review, and separate Build PPT/Build audio + subtitles/Build video stages. Video is locally reviewed after generation and has no separate approval. This document retains the broader architecture and MCP workflow reference.

This is the standalone automation project for generating narrated product videos locally from a product resource directory. Publishing is performed by the user outside this project.

## Quick summary

```text
Product resource directory
  → content/image/document inspection
  → PPTX generation or PPTX validation
  → English primary-language and configurable secondary-language Azure Neural Speech
  → Speech word-boundary metadata
  → PDF and slide rendering
  → English MP4
  → Mandarin MP4
  → bilingual dual-track MP4
  → subtitle artifacts
  → review
  → guarded GitHub Release publication
```

The MCP server exposes five operations. The Web GUI uses one selected product resource directory as both the resource root and access boundary; an explicit `video-project.json` is optional in that workflow:

| Tool | Purpose | Side effects |
|---|---|---|
| `list_product_resources` | List resource files below the allowed root | None |
| `scan_product_resources` | Categorize resources by type and filename convention | None |
| `inspect_video_project` | Validate the effective settings and source files | None |
| `build_video_project` | Generate PPTX, narration, subtitles, PDF, and videos | Azure Speech calls and local files |
| `publish_video_project` | Build and upload a GitHub Release | External Release mutation; explicitly gated |

## Optional Vision analysis

When product images are available, enable `vision_analysis` to extract visible text, image type, descriptions, key points, alt text, and suggested slide placement. The result is saved under `.video-work/vision-analysis.json`.

```json
{
  "vision_analysis": {
    "enabled": true,
    "provider": "openai-compatible",
    "model": "gpt-4.1",
    "base_url": "https://api.openai.com/v1",
    "require_review": true,
    "max_image_bytes": 5000000
  }
}
```

The Vision stage uses `VIDEO_VISION_API_KEY`, `OPENAI_API_KEY`, or `AZURE_OPENAI_API_KEY`. It is optional and review-gated. Its reviewed `suggested_slide` value controls image placement in generated PPTX slides. Without Vision analysis, the renderer uses deterministic image order. When the text LLM stage is enabled, the reviewed image analysis is included in the outline-generation input.

## Optional LLM content stage

The project can optionally use an LLM before PPTX generation:

```text
Product materials
  → LLM extracts product points
  → presentation outline
  → English primary narration
  → configurable secondary narration
  → human review
  → PPTX generation
  → speech and video generation
```

Configure it in `video-project.json`:

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

Use one of `VIDEO_LLM_API_KEY`, `OPENAI_API_KEY`, or `AZURE_OPENAI_API_KEY`. Azure OpenAI additionally requires `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_DEPLOYMENT`. The LLM returns a structured outline and both narration drafts. The draft is saved under `.video-work/content-draft.json`; the build stops until a human sets `VIDEO_MCP_APPROVE_DRAFT=true`.

## Resource contract

A reusable product directory can be self-contained:

```text
product-video/
├── video-project.json              # optional for the Web GUI
├── assets/
│   └── product-presentation.pptx
├── narration/
│   ├── narration.en.json
│   └── narration.zh-CN.json
├── subtitles/
│   └── summary.json
└── outputs/
```

Example configuration:

```json
{
  "name": "example-product-video",
  "version": "0.1.0",
  "sources": {
    "presentation": "assets/product-presentation.pptx",
    "narration_en": "narration/narration.en.json",
    "narration_zh": "narration/narration.zh-CN.json",
    "subtitles": "subtitles/summary.json"
  },
  "voices": {
    "english": "en-US-JennyNeural",
    "mandarin": "zh-CN-YunyangNeural"
  },
  "output": {
    "directory": "outputs",
    "gap_seconds": 0.5
  }
}
```

For the Web GUI, the selected resource directory immediately becomes `VIDEO_PROJECT_ROOT`, the access boundary, and the Pi working directory. Paths outside this selected directory are rejected. Credentials must never be placed in the resource directory. CLI users can set `VIDEO_PROJECT_ROOT` explicitly.

By default, the project automatically scans the resource directory and categorizes presentation, content, image, table, video, audio, narration, and subtitle files. Explicit lists in `video-project.json` override discovery. The primary language is always English; the secondary language defaults to `zh-CN` and can be changed to another Azure Speech locale. `output.target_duration_seconds` can be used to request a custom final duration.

## Installation

```bash
python3 -m venv .venv
./.venv/bin/pip install -e .
```

Required local tools for video rendering:

```text
LibreOffice / soffice
Poppler / pdftoppm
FFmpeg
```

CLI environment variable:

```bash
export VIDEO_PROJECT_ROOT=/path/to/product-resource
```

The Web GUI sets this session boundary automatically after the user selects a product resource directory.

Authenticate with Azure CLI before building:

```bash
az login
az account set --subscription "<subscription-id>"
```

The pipeline discovers the Speech resource, retrieves its key only in memory, and queries the supported TTS voice catalog. `AZURE_SPEECH_KEY` and `AZURE_SPEECH_REGION` are not required for normal local builds. A service principal or managed identity can replace Azure CLI when supported by the host.

Start the MCP server:

```bash
./.venv/bin/launchframe-mcp
```

## Build lifecycle

### 1. Read product materials and create the PPTX

The first stage reads the configured text/Markdown content and can use product images and reference documents. If `sources.presentation` is provided, the existing PPTX is validated and used. If it is `null`, the initial renderer creates a basic PPTX from `content_files`.

The generated deck is the source for the next stage. Video generation does not start until the PPTX exists.

### 2. Validate resources

The server checks:

- the selected resource directory is accessible;
- the presentation exists when one is required;
- English and Mandarin narration files exist;
- optional subtitle source exists;
- configured paths stay inside the product directory;
- the selected resource directory is the current `VIDEO_PROJECT_ROOT` boundary.

### 3. Authenticate Azure and choose the Speech resource

The GUI or MCP client calls `azure_login_status`, `discover_speech_resources`, and `list_tts_voices`. The user selects a Speech resource and a Voice for the primary and secondary languages. The selected resource ID may be stored in the explicit manifest or the application-managed session settings; the Speech key is never written there.

### 4. Generate narration

The Speech pipeline:

- always uses English as the primary language, defaulting to `en-US`;
- uses a configurable secondary locale, defaulting to `zh-CN`;
- selects the primary and secondary Azure voices from the effective project settings;
- emits one WAV file per slide and language;
- records `audio_offset`, `duration`, `text_offset`, `word_length`, and recognized boundary text;
- applies request pacing and transient retry behavior;
- writes manifests below `.video-work/`.

Default Speech pacing follows the Azure F0 limit:

```text
AZURE_SPEECH_MIN_REQUEST_INTERVAL_SECONDS=3.2
AZURE_SPEECH_MAX_RETRIES=5
AZURE_SPEECH_RETRY_BASE_SECONDS=4
```

### 5. Combine audio

For each slide, the longer language duration becomes the target duration. The shorter language is padded with silence. A configurable gap is added between slides. The result is two common-timeline audio tracks.

### 6. Render the presentation

The renderer checks for PowerPoint Desktop on Windows first. In `VIDEO_RENDERER=auto` mode (the default), it uses PowerPoint COM when available and otherwise falls back to LibreOffice. Set `VIDEO_RENDERER=libreoffice` to force the cross-platform renderer. The renderer converts the supplied PPTX to PDF, creates a visual video, and uses FFmpeg to generate:

```text
presentation-en.mp4
presentation-zh.mp4
presentation-dual.mp4
presentation.pdf
```

The current standalone project is intentionally resource-driven: the product supplies the PPTX, while the pipeline owns the speech, timing, rendering, and packaging lifecycle.

### 7. Review before publishing

Review:

- slide layout and fonts;
- English and Mandarin pronunciation;
- audio/video alignment;
- subtitle readability;
- output duration;
- filenames and project version.

On Windows, use `VIDEO_RENDERER=powerpoint` to require PowerPoint COM, or `VIDEO_RENDERER=libreoffice` to avoid Office. Do not publish automatically immediately after synthesis unless the team has accepted the generated content.

## Guarded publication

Publishing requires:

```bash
export VIDEO_MCP_ALLOW_PUBLISH=true
export GITHUB_TOKEN="<masked-token>"
export VIDEO_GITLAB_PROJECT_ID="<project-id>"
export VIDEO_RELEASE_HOST="https://github.com"
export VIDEO_RELEASE_REF="<source-ref>"
```

Then call:

```text
publish_video_project(project_dir, "1.0.0")
```

The publisher:

1. builds the project;
2. creates `presentation-v1.0.0`;
3. uploads files under the configured output directory to Generic Package Registry;
4. creates a GitHub Release;
5. adds package links to the Release.

The publish operation is rejected unless `VIDEO_MCP_ALLOW_PUBLISH=true`.

## Security and operational rules

- Keep Azure and GitHub tokens outside resource directories.
- Keep publishing disabled by default.
- Keep product paths inside `VIDEO_PROJECT_ROOT`.
- Do not use shell interpolation for resource paths.
- Review generated media before publication.
- Use immutable semantic versions for Releases.
- Keep generated videos out of Git history.
- Store large media in GitHub Package Registry, object storage, or an approved artifact storage.

## Migration from Dolphins MCP Toolkit

The original `vendor/azure-mcp/` directory remains the validated reference implementation for the current reference presentation. This standalone project provides the independent MCP boundary and resource contract. Migration work should progressively move the generic speech, subtitle, renderer, and Release logic here while keeping product-specific deck templates and narration resources in each product directory.
