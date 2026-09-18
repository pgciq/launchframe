# User workflow

## Product resource directory and access boundary

Each run selects one product resource directory. That directory is immediately used as the access boundary for the run; a separate workspace root is not required. The selected folder only needs product documents, images, tables, PDF/DOCX files, or a presentation; `video-project.json` is optional.

After selection, LaunchFrame sets the boundary, scans resources, and starts Pi automatically. Pi status is shown on the same line as the directory state. It creates run settings in the application-managed `.video-work/project-sessions/` area and does not require a project manifest in the user's resource folder.

Switching to another directory stops the current Pi instance, resets all run state, scans the new directory, and starts a fresh Pi instance. Azure authentication and Provider tokens are preserved across directory switches.

## Provider and Vision

Authenticate the selected Provider, choose a model, and save the configuration. Vision analysis processes all visual inputs from the resource directory:

- standalone image files;
- PDF and DOCX pages (rendered via PyMuPDF);
- PPTX slides (rendered via PowerPoint COM, macOS PowerPoint automation, or LibreOffice);
- video keyframes (extracted via FFmpeg, up to 12 per video, evenly spaced).

Review and approve Vision results before generating the Draft.

## Video and subtitle resources

Video files and co-located subtitle files are treated as product reference material, not as output. When Vision is enabled, keyframes from each video file are sent to the Vision model. When the Draft is generated, any `.srt` or `.vtt` file co-located with a video (same stem, any language suffix such as `demo.zh-CN.srt`) is read as transcript text and included in the LLM prompt alongside other content files.

## Draft

The Draft is the source for the PPT, narration, subtitles, and videos:

```text
Customize Draft Prompt → Generate Draft → Load/edit → Save Draft → Approve Draft
```

The Draft section has separate prompt controls:

- **Load saved prompt** restores the previously saved Draft prompt;
- editing the prompt immediately marks it as changed and enables **Save prompt**;
- loading over unsaved changes opens the themed confirmation dialog;
- the current prompt is used immediately by **Generate LLM draft**, even before it is saved.

Loading restores the saved file. Saving manual changes invalidates downstream outputs and explicit approvals; generated audio and subtitles are automatically accepted when regenerated.

## Build and review

```text
Customize PPT Prompt → Save PPT prompt → Build PPT → review PPT/PDF
Build audio + subtitles → review audio/subtitles (automatically accepted)
Build video → review locally → download or regenerate
```

The PPT prompt is edited in the Stage build and review section, directly above **Build PPT**. It has its own **Load saved prompt** and **Save PPT prompt** controls, so users do not need to return to the main configuration section. The GUI requires changed PPT prompt text to be saved before building. When starting audio from the GUI, the reviewed PPT stage is accepted automatically; standalone pipeline callers can still use the presentation approval gate.

Subtitle edits change captions and timing only. Spoken content changes must be made in the Draft and then regenerated as audio.

## Cancelling a running build

While a build is running, the active button pulses yellow. Click it a second time to open a confirmation dialog and cancel the operation. Cancellation stops the current stage; already-generated files are kept.
