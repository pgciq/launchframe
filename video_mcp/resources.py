from __future__ import annotations

import re
from pathlib import Path

CATEGORIES = {
    "presentation": {".pptx", ".ppt"},
    "content": {".md", ".txt", ".rst", ".pdf", ".docx", ".doc", ".eml", ".one", ".vsdx", ".vsd", ".pages", ".key", ".json", ".yaml", ".yml", ".xml"},
    "image": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".svg"},
    "table": {".csv", ".xlsx", ".xls", ".numbers"},
    "video": {".mp4", ".mov", ".webm", ".mkv", ".avi"},
    "audio": {".mp3", ".wav", ".m4a", ".flac", ".ogg"},
}
NARRATION_PATTERN = re.compile(r"^narration\.([A-Za-z]{2,3}(?:-[A-Za-z0-9]+)*)\.json$")
IGNORED_RESOURCE_DIRECTORIES = {".git", ".venv", ".video-work", "outputs", "__pycache__"}


def is_presentation_template(relative_path: str) -> bool:
    path = Path(relative_path)
    lowered_parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    return "templates" in lowered_parts or "template" in lowered_parts or name.endswith(".template.pptx") or name.endswith(".template.ppt")


def presentation_candidates(root: Path, output_dir: Path | None = None) -> list[str]:
    """Return user-provided PPT files, excluding generated output decks."""
    root = root.resolve()
    output_dir = (output_dir or root / "outputs").resolve()
    candidates: list[str] = []
    for relative in scan(root)["presentation"]:
        path = root / relative
        try:
            path.resolve().relative_to(output_dir)
        except ValueError:
            candidates.append(relative)
    return candidates


def scan(root: Path) -> dict[str, list[str]]:
    result = {category: [] for category in CATEGORIES}
    result["narration"] = []
    result["subtitle"] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in IGNORED_RESOURCE_DIRECTORIES for part in path.parts):
            continue
        relative = str(path.relative_to(root)).replace("\\", "/")
        if path.name == "video-project.json":
            continue
        if "subtitles" in path.parts or path.suffix.lower() in {".srt", ".vtt"}:
            result["subtitle"].append(relative)
            continue
        match = NARRATION_PATTERN.match(path.name)
        if match:
            result["narration"].append(relative)
            continue
        category = next((name for name, extensions in CATEGORIES.items() if path.suffix.lower() in extensions), None)
        if category:
            result[category].append(relative)
    return result
