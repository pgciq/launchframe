# Product resource layout

Each video run starts from one selected product resource directory. In the Web GUI, `video-project.json` is optional: LaunchFrame scans the selected directory and stores run settings in the application workspace. A `video-project.json` remains supported for explicit CLI and reusable example-project configurations.

```text
product-video/
├── video-project.json              # optional in the Web GUI
├── content/
│   ├── product-overview.md
│   └── technical-notes.md
├── assets/
│   ├── product-presentation.pptx   # optional existing deck (slides → LLM + Vision)
│   ├── demo/
│   │   ├── product-demo.mp4        # optional reference video (keyframes → Vision)
│   │   └── product-demo.zh-CN.srt  # optional co-located subtitle (text → LLM)
│   ├── images/                     # optional product images (→ Vision)
│   └── documents/                  # optional reference documents
├── narration/
│   ├── narration.en.json
│   └── narration.zh-CN.json
├── subtitles/
│   └── summary.json
└── outputs/
```

## Language and duration configuration

The project is internationalized by design:

- `primary_language` is always English and defaults to `en-US`;
- `secondary_language` accepts any supported Azure Speech locale and defaults to `zh-CN`;
- `voices.primary` and `voices.secondary` must match the selected locales;
- supported secondary examples include `zh-CN`, `ja-JP`, `ko-KR`, `de-DE`, `fr-FR`, and `es-ES`, subject to Azure Speech voice availability;
- `output.target_duration_seconds` is optional. When set, FFmpeg pitch-preserving `atempo` processing fits both narration tracks to the requested duration.

The target duration is a production constraint. Review speech naturalness if the requested duration differs substantially from the source narration duration.

Example:

```json
{
  "primary_language": "en-US",
  "secondary_language": "ja-JP",
  "voices": {
    "primary": "en-US-JennyNeural",
    "secondary": "ja-JP-NanamiNeural"
  },
  "output": {
    "target_duration_seconds": 300
  }
}
```

## Automatic resource scanning

By default, `sources.auto_scan` is enabled. The MCP server scans the product directory recursively and categorizes files by extension:

```text
presentation: .pptx, .ppt     → slide text + speaker notes extracted for LLM
                               → slides rendered as images for Vision
content:      .md, .txt, .rst, .pdf, .docx, .json, .yaml, .yml, .xml
                               → plain text extracted for LLM
                               → PDF / DOCX pages rendered for Vision
image:        .png, .jpg, .jpeg, .webp, .bmp, .tif, .tiff, .svg
                               → sent directly to Vision
table:        .csv, .xlsx, .xls
                               → tabular text extracted for LLM
video:        .mp4, .mov, .webm, .mkv, .avi
                               → keyframes extracted (FFmpeg) for Vision
                               → co-located .srt/.vtt transcript text → LLM
audio:        .mp3, .wav, .m4a, .flac, .ogg
                               → scanned and listed; not yet processed
narration:    narration.<locale>.json
subtitle:     .srt, .vtt      → co-located with a video: transcript → LLM
                               → in content_files: text extracted for LLM
```

The scanner ignores `.git`, `.venv`, `.video-work`, `outputs`, and Python cache directories. When present, explicit lists in `video-project.json` override automatic discovery. Without it, the Web GUI uses automatic discovery and stores only user settings in its internal workspace session. Use `scan_product_resources` to inspect the categorization before building.

## Two presentation entry modes

### Mode A: One or more existing PPTX files

For one source deck, set `sources.presentation`:

```json
"presentation": "assets/product-presentation.pptx"
```

For multiple PPTX files used as LLM reference material, set `sources.presentation_sources`:

```json
"presentation_sources": [
  "assets/product-overview.pptx",
  "assets/architecture.pptx",
  "assets/roadmap.pptx"
]
```

A single selected source PPT is reused as the presentation. Multiple source PPTs are parsed for text and notes, then a new `outputs/presentation.pptx` is generated. Do not use the same file as both a source PPT and a template.

### Mode B: Generate the PPTX first

Set `sources.presentation` to `null` and provide Markdown content files:

```json
"presentation": null,
"content_files": [
  "content/product-overview.md",
  "content/technical-notes.pdf"
],
"images": [
  "assets/images/product-screenshot.png"
],
"tables": [
  "data/product-metrics.xlsx"
],
"videos": [
  "assets/demo/product-demo.mp4"
],
"audio": [
  "assets/audio/interview.mp3"
]
```

The first pipeline stage creates a basic PPTX from headings, paragraphs, and bullet lists. With Vision analysis enabled, reviewed `suggested_slide` results determine where configured images are placed; without Vision analysis, images fall back to deterministic list order. Markdown, text, PDF, and DOCX content files are supported as text inputs. Product-specific templates, branding, chart layouts, and richer document extraction can be added later without changing the MCP resource contract.

## Required resources

For the **Web GUI** workflow, `video-project.json` is optional. The GUI scans the selected directory and keeps settings in its internal `.video-work/project-sessions/` area. The only hard requirement is that the resource directory contains at least one supported content file (document, image, table, PDF/DOCX, or presentation) before starting the build.

For the **CLI / explicit manifest** workflow:

- `video-project.json`;
- either an existing PPTX or at least one `content_files` entry;
- `narration/narration.en.json` for the primary language;
- `narration/narration.zh-CN.json` for the default secondary language, or another file for the configured secondary language.

Narration files are arrays of objects with `slide`, `title`, and `text`. When an automatically generated deck is used, the narration slide numbers must match the generated slide order.

## Supported file types

| Category | Extensions | How it is used |
|----------|-----------|----------------|
| Text | `.md` `.txt` `.rst` | Full text → LLM |
| Documents | `.pdf` `.docx` `.doc` `.eml` `.one` `.vsdx` `.vsd` `.pages` `.key` | Text → LLM; supported Office/iWork pages rendered as images → Vision |
| Structured data | `.json` `.yaml` `.yml` `.xml` | Parsed text → LLM |
| Tables | `.csv` `.xlsx` `.xls` `.numbers` | Row/column text → LLM; supported spreadsheet pages rendered → Vision |
| Subtitles | `.srt` `.vtt` | Plain narration text → LLM |
| Images | `.png` `.jpg` `.jpeg` `.webp` `.bmp` `.tif` `.tiff` | Sent to Vision model |
| Presentation | `.pptx` `.ppt` | Slide text + notes → LLM; slides rendered → Vision; used as source deck |
| Video | `.mp4` `.mov` `.webm` `.mkv` `.avi` | Keyframes extracted (FFmpeg, ≤12 per video) → Vision; co-located `.srt`/`.vtt` → LLM |
| Audio | `.mp3` `.wav` `.m4a` `.flac` `.ogg` | Scanned and listed; not yet processed for content |

## Images and documents

Images and reference documents are product inputs. The initial renderer can place configured images and extract text from Markdown, text, PDF, DOCX, PPTX, SRT, and VTT files. The files below `assets/images/` and `assets/documents/` can be used for:

- product screenshots;
- architecture diagrams;
- charts;
- PDF/document summaries;
- branding assets.

## Video and subtitle resources

Video files placed in the resource directory are automatically processed for Vision analysis: LaunchFrame extracts up to 12 evenly-spaced keyframes using FFmpeg and sends each frame to the Vision model labelled with its timestamp. Co-located subtitle files (same stem, `.srt` or `.vtt`) are read as plain transcript text and included in the LLM prompt.

Example with a 60-second demo video:

```text
assets/demo/product-demo.mp4       → 12 frames at ~5-second intervals
assets/demo/product-demo.srt       → transcript text for LLM
assets/demo/product-demo.zh-CN.srt → Chinese transcript for LLM
```

## Existing PPTX resources

When a `.pptx` file is found in the resource directory, it is used in three ways:

1. **Slide text for LLM**: every slide's title, body paragraphs, and speaker notes are extracted using python-pptx and prepended to the LLM prompt, so generated narration aligns with the actual slide content.
2. **Slides for Vision**: each slide is rendered as a 2× PNG image via PowerPoint COM on Windows, PowerPoint automation on macOS when available, or the LibreOffice fallback, and sent to the Vision model labelled as `slide N of filename.pptx`.
3. **Source deck**: the PPTX is used directly as the presentation source for audio, subtitle, and video generation, bypassing the PPT generation stage.

The MCP resource-list tool reports these files without exposing their contents automatically.

## Security boundary

## Azure MCP source

The project includes `azure-mcp` under `vendor/azure-mcp/`, copied from the main Toolkit repository:

```json
{
  "azure": {
    "checkout_dir": "vendor/azure-mcp"
  }
}
```

The first Azure operation installs the bundled `azure-mcp` into the active Python environment and launches it over MCP stdio. The repository/ref fields remain available for development updates, but normal execution does not clone the external repository. Keep the vendored source aligned with a reviewed main-repository Commit or Tag.

The video project calls `azure_auth_status`, `list_resources`, and Azure resource discovery through `azure-mcp`. It then calls ARM `listKeys` using the authenticated Azure identity, keeps the Speech key in memory, and queries the Speech Voice catalog. The key is never returned by an MCP tool or written to `video-project.json`.

The MCP server accepts only project directories under `VIDEO_PROJECT_ROOT`:

```bash
export VIDEO_PROJECT_ROOT=/path/to/product-projects
```

It rejects paths outside that root and does not use shell interpolation for paths. Do not place secrets inside a product resource directory. Azure and GitHub credentials must come from the environment or CI/CD variables.
