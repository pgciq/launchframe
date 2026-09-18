from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .presentation import _read_document, _read_subtitle

_DRAFT_SCHEMA = (
    '{\n'
    '  "outline": [{"slide": 1, "title": "...", "key_points": ["..."]}],\n'
    '  "primary_narration": [{"slide": 1, "title": "...", "text": "..."}],\n'
    '  "secondary_narration": [{"slide": 1, "title": "...", "text": "..."}]\n'
    '}'
)

_DRAFT_BASE_PROMPT = (
    "Create a presentation content draft from the product materials."
    " Return JSON only with this schema:\n"
    + _DRAFT_SCHEMA
    + "\nThe primary language is English. The secondary language is configured separately."
    " Do not invent unsupported product facts. Keep slide numbers aligned across all arrays."
)


def _video_transcripts(video: Path) -> list[Path]:
    """Return co-located .srt/.vtt files whose stem starts with the video stem."""
    found: list[Path] = []
    try:
        for p in sorted(video.parent.iterdir()):
            if p.suffix.lower() in {".srt", ".vtt"} and p.stem.startswith(video.stem):
                found.append(p)
    except OSError:
        pass
    return found


def _api_url(provider: str, base_url: str | None) -> str:
    if provider == "azure-openai":
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
        if not endpoint or not deployment:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT are required")
        return f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    return f"{(base_url or os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')).rstrip('/')}/chat/completions"


def generate_content_draft(config: Any, work_dir: Path) -> dict[str, Any]:
    key = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("VIDEO_LLM_API_KEY")
    if not key:
        raise RuntimeError("An LLM API key or authenticated Pi provider is required for content generation")
    material: list[str] = []
    if config.presentation and config.presentation.exists():
        material.append(f"\n--- {config.presentation.name} (existing presentation) ---\n{_read_document(config.presentation)}")
    for presentation in getattr(config, "presentation_sources", ()):
        if presentation.exists():
            material.append(f"\n--- {presentation.name} (reference presentation) ---\n{_read_document(presentation)}")
    for path in config.content_files + config.table_files:
        material.append(f"\n--- {path.name} ---\n{_read_document(path)}")
    for path in config.image_files:
        material.append(f"\n--- image asset ---\n{path.name}")
    for video in config.video_files:
        transcripts = _video_transcripts(video)
        if transcripts:
            for sub in transcripts:
                material.append(f"\n--- {video.name} (transcript: {sub.name}) ---\n{_read_subtitle(sub)}")
    vision_path = work_dir / "vision-analysis.json"
    if vision_path.exists():
        material.append(f"\n--- vision analysis ---\n{vision_path.read_text(encoding='utf-8')}")
    if not material:
        raise ValueError("No product materials were discovered for LLM content generation")

    # 估算 token 用量并给出警告
    total_chars = sum(len(m) for m in material)
    estimated_tokens = total_chars // 2  # 粗略估算：1 token ≈ 2 chars
    if estimated_tokens > 30_000:
        import warnings
        warnings.warn(
            f"项目素材较多（~{estimated_tokens // 1000}K tokens），可能导致 LLM 响应质量下降。"
            f"建议减少 content 文件数量或将大文件拆分，控制在 20K tokens 以内以获得最佳效果。",
            stacklevel=2,
        )
    elif estimated_tokens > 15_000:
        import warnings
        warnings.warn(
            f"项目素材约 {estimated_tokens // 1000}K tokens，正在生成内容草稿，可能需要较长时间。",
            stacklevel=2,
        )

    extra = getattr(config, "draft_instructions", "").strip()
    prompt = _DRAFT_BASE_PROMPT + ("\n\nAdditional instructions:\n" + extra if extra else "")
    payload = {
        "model": config.content_generation.model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": "\n".join(material)}],
    }
    headers = {"Content-Type": "application/json"}
    if config.content_generation.provider == "azure-openai":
        headers["api-key"] = key
    else:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(_api_url(config.content_generation.provider, config.content_generation.base_url), data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"LLM content generation failed: {error.code}: {error.read().decode(errors='replace')}") from error
    content = result["choices"][0]["message"]["content"]
    draft = json.loads(content) if isinstance(content, str) else content
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "content-draft.json").write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    (work_dir / "narration-primary.json").write_text(json.dumps(draft["primary_narration"], ensure_ascii=False, indent=2), encoding="utf-8")
    (work_dir / "narration-secondary.json").write_text(json.dumps(draft["secondary_narration"], ensure_ascii=False, indent=2), encoding="utf-8")
    return draft
