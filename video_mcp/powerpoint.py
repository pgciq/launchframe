from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

POWERSHELL_SCRIPT = Path(__file__).with_name("powerpoint_render.ps1")


def powerpoint_executable() -> str | None:
    candidates = [
        shutil.which("POWERPNT.EXE"),
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Microsoft Office/root/Office16/POWERPNT.EXE",
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Microsoft Office/root/Office16/POWERPNT.EXE",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def mac_powerpoint_app() -> str | None:
    """Return the installed macOS PowerPoint app, if it can be found."""
    if sys.platform != "darwin":
        return None
    candidates = [
        Path("/Applications/Microsoft PowerPoint.app"),
        Path.home() / "Applications/Microsoft PowerPoint.app",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    # Office can be installed in a non-standard location. Spotlight is a
    # cheap, read-only fallback and is available on normal macOS installs.
    mdfind = shutil.which("mdfind")
    if mdfind:
        result = subprocess.run(
            [mdfind, "kMDItemCFBundleIdentifier == 'com.microsoft.Powerpoint'"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            candidate = Path(line.strip())
            if candidate.name == "Microsoft PowerPoint.app" and candidate.exists():
                return str(candidate)
    return None


def is_macos() -> bool:
    return sys.platform == "darwin"


def available() -> bool:
    if os.name == "nt":
        return bool(powerpoint_executable()) and bool(shutil.which("powershell.exe"))
    return is_macos() and bool(mac_powerpoint_app()) and bool(shutil.which("osascript"))


def _applescript_path(path: Path) -> str:
    # AppleScript strings use backslash escaping, just like the paths passed
    # to POSIX file. Keep this local rather than invoking a shell.
    return str(path.resolve()).replace("\\", "\\\\").replace('"', '\\"')


def export_pdf_macos(presentation: Path, pdf: Path) -> None:
    """Use PowerPoint for Mac to export a presentation as PDF."""
    if not is_macos() or not mac_powerpoint_app() or not shutil.which("osascript"):
        raise RuntimeError("Microsoft PowerPoint for Mac is not available")
    pdf.parent.mkdir(parents=True, exist_ok=True)
    destination = _applescript_path(pdf)
    app = mac_powerpoint_app()
    open_result = subprocess.run(
        ["open", "-a", app, str(presentation.resolve())],
        capture_output=True,
        text=True,
        check=False,
    )
    if open_result.returncode:
        detail = (open_result.stderr or open_result.stdout).strip()
        raise RuntimeError(f"PowerPoint for Mac could not open {presentation.name}. {detail}")
    script = f'''\
 tell application "Microsoft PowerPoint"
     set targetPresentation to missing value
     repeat 60 times
         try
             set targetPresentation to active presentation
             if targetPresentation is not missing value then exit repeat
         on error
             set targetPresentation to missing value
         end try
         delay 0.5
     end repeat
     if targetPresentation is missing value then error "PowerPoint did not open the presentation"
     set pdfFile to POSIX file "{destination}"
     save targetPresentation in pdfFile as save as PDF
     close targetPresentation saving no
 end tell
'''
    result = subprocess.run(
        ["osascript", "-"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode or not pdf.exists():
        detail = (result.stderr or result.stdout).strip()
        hint = "Allow the terminal or application to control Microsoft PowerPoint in System Settings > Privacy & Security > Automation."
        raise RuntimeError(f"PowerPoint for Mac could not export {presentation.name} to PDF. {detail or hint}")


def render(presentation: Path, pdf: Path, visual: Path, slide_durations: list[float]) -> None:
    if not available():
        raise RuntimeError("Microsoft PowerPoint Desktop is not available")
    if is_macos():
        # PowerPoint for Mac does not expose the Windows COM CreateVideo API.
        # The caller renders this PDF to frames and lets FFmpeg build the MP4.
        export_pdf_macos(presentation, pdf)
        return
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as durations_file:
        json.dump(slide_durations, durations_file)
        durations_path = Path(durations_file.name)
    try:
        subprocess.run([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(POWERSHELL_SCRIPT),
            "-Source", str(presentation),
            "-Pdf", str(pdf),
            "-Visual", str(visual),
            "-Durations", str(durations_path),
        ], check=True)
    finally:
        durations_path.unlink(missing_ok=True)
