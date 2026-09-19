from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .resources import is_presentation_template, scan

CONFIG_NAME = "video-project.json"


@dataclass(frozen=True)
class ContentGenerationConfig:
    provider: str
    model: str
    base_url: str | None
    require_review: bool


@dataclass(frozen=True)
class VisionConfig:
    enabled: bool
    provider: str
    model: str
    base_url: str | None
    require_review: bool
    max_image_bytes: int
    max_keyframes: int = 8
    max_vision_images: int = 20


@dataclass(frozen=True)
class AzureConfig:
    subscription_id: str | None
    speech_resource_id: str | None
    repository: str
    ref: str
    checkout_dir: str


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    name: str
    version: str
    presentation: Path | None
    content_files: tuple[Path, ...]
    image_files: tuple[Path, ...]
    table_files: tuple[Path, ...]
    video_files: tuple[Path, ...]
    audio_files: tuple[Path, ...]
    narration_primary: Path
    narration_secondary: Path
    primary_language: str
    secondary_language: str
    subtitles: Path | None
    output_dir: Path
    gap_seconds: float
    primary_voice: str
    secondary_voice: str
    target_duration_seconds: float | None
    content_generation: ContentGenerationConfig
    vision: VisionConfig
    azure: AzureConfig
    draft_instructions: str
    presentation_template: Path | None
    presentation_sources: tuple[Path, ...] = ()
    presentation_instructions: str = ""


def allowed_root() -> Path:
    return Path(os.getenv("VIDEO_PROJECT_ROOT", Path.cwd())).resolve()


def contained(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def project_path(project_dir: str | Path) -> Path:
    root = allowed_root()
    path = Path(project_dir).expanduser().resolve()
    if not contained(root, path):
        raise PermissionError(f"Project path is outside VIDEO_PROJECT_ROOT: {path}")
    if not path.is_dir():
        raise ValueError(f"Project directory does not exist: {path}")
    return path


def relative_file(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if not contained(root, path):
        raise ValueError(f"Configured file escapes project directory: {value}")
    return path


def managed_config_path(root: Path) -> Path:
    """Return the internal settings path for a resource-only project."""
    digest = hashlib.sha256(str(root.resolve()).encode("utf-8")).hexdigest()[:24]
    path = allowed_root() / ".video-work" / "project-sessions" / f"{digest}.json"
    if not contained(allowed_root(), path):
        raise ValueError("Managed project settings path escapes the allowed workspace")
    return path


def project_settings(root: Path) -> tuple[dict[str, Any], Path, bool]:
    """Load explicit project settings or the internal settings for a resource folder."""
    explicit = root / CONFIG_NAME
    managed = managed_config_path(root)
    if explicit.exists():
        return json.loads(explicit.read_text(encoding="utf-8")), explicit, False
    if managed.exists():
        return json.loads(managed.read_text(encoding="utf-8")), managed, True
    defaults = {
        "source_root": str(root.resolve()),
        "name": root.name,
        "version": "0.1.0",
        "primary_language": "en-US",
        "secondary_language": "zh-CN",
        "sources": {"auto_scan": True},
        "voices": {"primary": "en-US-JennyNeural", "secondary": "zh-CN-YunyangNeural"},
        "content_generation": {"provider": "openai", "model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1", "require_review": True},
        "vision_analysis": {"enabled": True, "provider": "openai", "model": "gpt-4o-mini", "base_url": "https://api.openai.com/v1", "require_review": True, "max_image_bytes": 5_000_000, "max_keyframes": 8, "max_vision_images": 20},
        "azure": {"repository": "", "ref": "", "checkout_dir": "vendor/azure-mcp"},
        "output": {"directory": "outputs", "gap_seconds": 0.5},
    }
    managed.parent.mkdir(parents=True, exist_ok=True)
    managed.write_text(json.dumps(defaults, ensure_ascii=False, indent=2), encoding="utf-8")
    return defaults, managed, True


def save_project_settings(root: Path, raw: dict[str, Any]) -> Path:
    """Persist settings without requiring a video-project.json in the user's folder."""
    explicit = root / CONFIG_NAME
    managed = managed_config_path(root)
    path = explicit if explicit.exists() else managed
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = dict(raw)
    if path == managed:
        raw["source_root"] = str(root.resolve())
    else:
        raw.pop("source_root", None)
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_project(project_dir: str | Path) -> ProjectConfig:
    root = project_path(project_dir)
    raw, _, _ = project_settings(root)
    sources = raw.get("sources", {})
    discovered = scan(root) if sources.get("auto_scan", True) else {category: [] for category in ("presentation", "content", "image", "table", "video", "audio", "narration", "subtitle")}
    voices = raw.get("voices", {})
    output = raw.get("output", {})
    content_generation = raw.get("content_generation", {})
    vision = raw.get("vision_analysis", {})
    azure = raw.get("azure", {})
    discovered_narration = discovered["narration"]
    primary_discovered = next((path for path in discovered_narration if ".en" in Path(path).name or ".en-" in Path(path).name), None)
    secondary_discovered = next((path for path in discovered_narration if path != primary_discovered and ".zh" in Path(path).name), None)
    primary_path = sources.get("narration_primary") or sources.get("narration_en") or primary_discovered or ".video-work/narration-primary.json"
    secondary_path = sources.get("narration_secondary") or sources.get("narration_zh") or secondary_discovered or next((path for path in discovered_narration if path != primary_discovered), None) or ".video-work/narration-secondary.json"
    presentation_candidates = [path for path in discovered["presentation"] if not is_presentation_template(path)]
    presentation_setting = sources.get("presentation")
    presentation_source_settings = sources.get("presentation_sources") or []
    if presentation_source_settings:
        presentation_sources = tuple(relative_file(root, str(value)) for value in presentation_source_settings)
        presentation_path = ""
    else:
        presentation_sources = ()
        presentation_path = presentation_setting or (presentation_candidates[0] if len(presentation_candidates) == 1 else "")
    return ProjectConfig(
        root=root,
        name=str(raw.get("name", root.name)),
        version=str(raw.get("version", "0.1.0")),
        presentation=relative_file(root, str(presentation_path)) if presentation_path else None,
        content_files=tuple(relative_file(root, str(value)) for value in (sources.get("content_files") or discovered["content"])),
        image_files=tuple(relative_file(root, str(value)) for value in (sources.get("images") or discovered["image"])),
        table_files=tuple(relative_file(root, str(value)) for value in (sources.get("tables") or discovered["table"])),
        video_files=tuple(relative_file(root, str(value)) for value in (sources.get("videos") or discovered["video"])),
        audio_files=tuple(relative_file(root, str(value)) for value in (sources.get("audio") or discovered["audio"])),
        narration_primary=relative_file(root, str(primary_path)),
        narration_secondary=relative_file(root, str(secondary_path)),
        primary_language=str(raw.get("primary_language", "en-US")),
        secondary_language=str(raw.get("secondary_language", "zh-CN")),
        subtitles=relative_file(root, str(sources["subtitles"])) if sources.get("subtitles") else None,
        output_dir=relative_file(root, str(output.get("directory", "outputs"))),
        gap_seconds=float(output.get("gap_seconds", 0.5)),
        primary_voice=str(voices.get("primary", voices.get("english", "en-US-JennyNeural"))),
        secondary_voice=str(voices.get("secondary", voices.get("mandarin", "zh-CN-YunyangNeural"))),
        target_duration_seconds=(float(output["target_duration_seconds"]) if output.get("target_duration_seconds") else None),
        content_generation=ContentGenerationConfig(
            provider=str(content_generation.get("provider", "openai")),
            model=str(content_generation.get("model", "gpt-4o-mini")),
            base_url=content_generation.get("base_url"),
            require_review=bool(content_generation.get("require_review", True)),
        ),
        vision=VisionConfig(
            enabled=bool(vision.get("enabled", True)),
            provider=str(vision.get("provider", "openai")),
            model=str(vision.get("model", "gpt-4o-mini")),
            base_url=vision.get("base_url"),
            require_review=True,
            max_image_bytes=int(vision.get("max_image_bytes", 5_000_000)),
            max_keyframes=int(vision.get("max_keyframes", 8)),
            max_vision_images=int(vision.get("max_vision_images", 20)),
        ),
        azure=AzureConfig(
            subscription_id=azure.get("subscription_id"),
            speech_resource_id=azure.get("speech_resource_id"),
            repository=str(azure.get("repository", "")),
            ref=str(azure.get("ref", "main")),
            checkout_dir=str(azure.get("checkout_dir", "vendor/azure-mcp")),
        ),
        draft_instructions=str(raw.get("draft_instructions", "")),
        presentation_template=relative_file(root, str(raw["presentation_template"])) if raw.get("presentation_template") else None,
        presentation_sources=presentation_sources,
        presentation_instructions=str(raw.get("presentation_instructions", "")),
    )


def validate_project(config: ProjectConfig) -> list[str]:
    errors: list[str] = []
    for name, path in {
        "presentation": config.presentation,
        "narration_primary": config.narration_primary,
        "narration_secondary": config.narration_secondary,
    }.items():
        if path is not None and not path.exists():
            # Narration is generated after the reviewed LLM Draft for folders
            # that contain only product resources.
            if name in {"narration_primary", "narration_secondary"} and path.parent == config.root / ".video-work":
                continue
            errors.append(f"Missing {name}: {path.relative_to(config.root)}")
    if config.primary_language.lower() not in {"en", "en-us", "en-gb"}:
        errors.append("primary_language must be English")
    if config.target_duration_seconds is not None and config.target_duration_seconds < 30:
        errors.append("output.target_duration_seconds must be at least 30")
    if config.presentation is None and not config.presentation_sources and not config.content_files and not config.image_files and not config.table_files:
        errors.append("Configure sources.presentation, sources.presentation_sources, sources.content_files, images, or tables")
    for name, paths in {
        "content": config.content_files,
        "images": config.image_files,
        "tables": config.table_files,
        "videos": config.video_files,
        "audio": config.audio_files,
    }.items():
        for path in paths:
            if not path.exists():
                errors.append(f"Missing {name} file: {path.relative_to(config.root)}")
    if config.subtitles and not config.subtitles.exists():
        errors.append(f"Missing subtitles: {config.subtitles.relative_to(config.root)}")
    if config.gap_seconds < 0 or config.gap_seconds > 10:
        errors.append("output.gap_seconds must be between 0 and 10")
    return errors
