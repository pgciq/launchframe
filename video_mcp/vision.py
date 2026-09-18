from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .llm import _api_url

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def _key() -> str:
    value = os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("VIDEO_VISION_API_KEY")
    if not value:
        raise RuntimeError("An Azure OpenAI or OpenAI-compatible Vision API key is required")
    return value


def analyze_images(config: Any, work_dir: Path) -> list[dict[str, Any]]:
    if not config.image_files:
        return []
    key = _key()
    work_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    max_images = getattr(config, "max_vision_images", 20)
    images_to_process = list(config.image_files)[:max_images]
    if len(config.image_files) > max_images:
        import warnings
        warnings.warn(
            f"发现 {len(config.image_files)} 个图片文件，但最多只分析前 {max_images} 张（vision_analysis.max_vision_images）。"
            f"超出部分将不会出现在演示幻灯片中。",
            stacklevel=2,
        )
    for image in images_to_process:
        if image.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if image.stat().st_size > config.vision.max_image_bytes:
            raise ValueError(f"Image exceeds vision size limit: {image}")
        mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
        encoded = base64.b64encode(image.read_bytes()).decode("ascii")
        prompt = (
            "Analyze this product image for a presentation. Return JSON only with: "
            "type, description, visible_text, key_points, alt_text, suggested_slide, confidence. "
            "Do not invent facts that are not visible."
        )
        payload = {
            "model": config.vision.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "high"}},
                ],
            }],
        }
        headers = {"Content-Type": "application/json"}
        if config.vision.provider == "azure-openai":
            headers["api-key"] = key
        else:
            headers["Authorization"] = f"Bearer {key}"
        request = urllib.request.Request(_api_url(config.vision.provider, config.vision.base_url), data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Vision analysis failed for {image.name}: {error.code}: {error.read().decode(errors='replace')}") from error
        analysis = json.loads(raw["choices"][0]["message"]["content"])
        # Store relative path so the frontend /api/file endpoint can serve it
        try:
            analysis["file"] = str(image.relative_to(config.root))
        except ValueError:
            analysis["file"] = str(image)
        results.append(analysis)
    output = work_dir / "vision-analysis.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results
