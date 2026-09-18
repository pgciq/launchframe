# Promotion and demo video

LaunchFrame can generate its own product promotional video. Treat that video as a demo deliverable, not as source code.

## Recommended location

Keep the demo project's source materials in the repository, for example:

```text
examples/product-video/
```

Generate media locally. Do not commit the resulting MP4, WAV, PDF, or PPTX to Git.

Store the approved demo video in one of:

- the company's internal video/media platform;
- GitLab Package Registry or Release assets;
- an approved internal file share.

The Pages documentation should contain a link to the approved video or an embed URL, not a large binary file. The link can be updated without changing the source repository.

## Interface screenshots

Starter screenshots are stored under:

```text
examples/product-video/assets/screenshots/
```

Current captures include:

```text
01-overview.png
02-resource-and-draft-workflow.png
03-build-review-workflow.png
```

Refresh these captures after a clean demo run and redact any account IDs, tokens, internal paths, quotas, and logs before publishing them.

## Suggested demo deliverables

```text
LaunchFrame overview MP4
English MP4
Secondary-language MP4
Dual-track MP4
Bilingual WebVTT
PPTX and PDF preview
```

The project does not upload or publish the video automatically. A user reviews the local output and publishes it through the normal company process.
