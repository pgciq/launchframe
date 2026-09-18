from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_APPLICATIONS = {
    "pages": ("Pages", "com.apple.Pages"),
    "numbers": ("Numbers", "com.apple.Numbers"),
    "keynote": ("Keynote", "com.apple.Keynote"),
    "onenote": ("Microsoft OneNote", "com.microsoft.onenote.mac"),
}


def mac_app(kind: str) -> str | None:
    if sys.platform != "darwin":
        return None
    try:
        name, bundle_id = _APPLICATIONS[kind]
    except KeyError as error:
        raise ValueError(f"Unsupported macOS document application: {kind}") from error
    candidates = [Path(f"/Applications/{name}.app"), Path.home() / f"Applications/{name}.app"]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    mdfind = shutil.which("mdfind")
    if mdfind:
        result = subprocess.run(
            [mdfind, f"kMDItemCFBundleIdentifier == '{bundle_id}'"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            candidate = Path(line.strip())
            if candidate.exists():
                return str(candidate)
    return None


def available(kind: str) -> bool:
    return bool(mac_app(kind)) and bool(shutil.which("open")) and bool(shutil.which("osascript"))


def export_pdf(source: Path, destination: Path, kind: str) -> None:
    """Export a Pages, Numbers, or Keynote file as PDF using macOS automation."""
    app = mac_app(kind)
    if sys.platform != "darwin" or not app or not shutil.which("open") or not shutil.which("osascript"):
        raise RuntimeError(f"Apple {kind.title()} is not available")
    application_name, bundle_id = _APPLICATIONS[kind]
    destination.parent.mkdir(parents=True, exist_ok=True)
    path = str(destination.resolve()).replace("\\", "\\\\").replace('"', '\\"')
    script = f'''\
 tell application id "{bundle_id}"
     set targetObject to missing value
     repeat 60 times
         try
             set targetObject to front document
             if targetObject is not missing value then exit repeat
         on error
             set targetObject to missing value
         end try
         delay 0.5
     end repeat
     if targetObject is missing value then error "Apple application did not open the source file"
     set pdfFile to POSIX file "{path}"
     export targetObject to pdfFile as PDF
     close targetObject saving no
 end tell
'''
    opened = subprocess.run(
        ["open", "-a", app, str(source.resolve())],
        capture_output=True,
        text=True,
        check=False,
    )
    if opened.returncode:
        detail = (opened.stderr or opened.stdout).strip()
        raise RuntimeError(f"Apple {kind.title()} could not open {source.name}. {detail}")
    result = subprocess.run(
        ["osascript", "-"], input=script, text=True, capture_output=True, check=False,
    )
    if result.returncode or not destination.exists():
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"Apple {kind.title()} could not export {source.name} to PDF. {detail}")
