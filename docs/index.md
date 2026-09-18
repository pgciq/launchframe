# LaunchFrame

LaunchFrame is a review-gated workspace for creating multilingual product promotional videos from product documents, images, tables, and presentations.

```
📁 Product resources
   docs · images · tables
   PPTX  → slide text → LLM  +  slides → Vision
   video → keyframes → Vision  +  .srt/.vtt → LLM
          │
          ▼
   □ Vision analysis  (optional)   →  👤 Approve
   □ LLM Draft                      →  👤 Approve
   □ Build PPT + PDF                →  👤 Review
   □ Azure Neural TTS + Subtitles   →  automatically accepted
   □ Render video (FFmpeg)          →  👤 local review
          │
          ▼
   primary.mp4  ·  secondary.mp4  ·  dual-track.mp4
   →  👤 local review  →  📤 upload manually
```

Every stage produces locally reviewable artifacts. Vision and Draft are explicit GUI approval gates; PPT/PDF is reviewed before audio generation, while audio/subtitles are automatically accepted and video is reviewed locally. Publishing is intentionally outside this project.

## Start here

- [Quick start](quick-start.md)
- [User workflow](user-workflow.md)
- [Complete pipeline diagram](pipeline.md)
- [Frequently asked questions](faq.md) · [常见问题解答](faq.zh-CN.md)
- [Provider and model setup](providers.md)
- [Resource layout](RESOURCE_LAYOUT.md)
- [First release guide](FIRST_RELEASE.md)
- [Troubleshooting](troubleshooting.md)
- [Promotion and demo video](promotion.md)

The project generates and reviews media locally. Users upload approved videos to the destination website using the normal company process.
