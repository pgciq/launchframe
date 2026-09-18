from __future__ import annotations

import hashlib
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
RELEASE = ROOT / "release"
TAG = os.getenv("CI_COMMIT_TAG") or os.getenv("RELEASE_VERSION") or "snapshot"

EXCLUDED_PARTS = {".git", ".venv", ".video-work", "outputs", "public", "dist", "__pycache__", ".ruff_cache", ".pi/npm", ".tools"}


def included_source(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in EXCLUDED_PARTS for part in relative.parts) or relative.as_posix().startswith(".pi/npm/"):
        return False
    return path.suffix not in {".pyc", ".pyo"}


def zip_paths(destination: Path, paths: list[Path], base: Path) -> None:
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.is_file():
                archive.write(path, path.relative_to(base).as_posix())


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


RELEASE.mkdir(parents=True, exist_ok=True)
source_path = RELEASE / f"launchframe-{TAG}-source.zip"
source_files = [path for path in ROOT.rglob("*") if path.is_file() and included_source(path)]
zip_paths(source_path, source_files, ROOT)

# FFmpeg is downloaded separately by tools/install-ffmpeg.ps1 and is not packaged with the source.
for stale_tools_path in RELEASE.glob("*-windows-tools.zip"):
    stale_tools_path.unlink()

artifacts = sorted(RELEASE.glob("*.zip")) + sorted((ROOT / "dist").glob("*"))
checksums = RELEASE / "SHA256SUMS.txt"
checksums.write_text("\n".join(f"{digest(path)}  {path.name}" for path in artifacts) + "\n", encoding="utf-8")
print(f"Created {source_path}")
print(f"Created {checksums}")
