from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


_APPLICATIONS = {
    "word": ("Microsoft Word", "com.microsoft.Word"),
    "excel": ("Microsoft Excel", "com.microsoft.Excel"),
}


def mac_office_app(kind: str) -> str | None:
    """Find a Microsoft Office application installed on macOS."""
    if sys.platform != "darwin":
        return None
    try:
        application_name, bundle_id = _APPLICATIONS[kind]
    except KeyError as error:
        raise ValueError(f"Unsupported macOS Office application: {kind}") from error
    candidates = [
        Path(f"/Applications/{application_name}.app"),
        Path.home() / f"Applications/{application_name}.app",
    ]
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
            if candidate.name == f"{application_name}.app" and candidate.exists():
                return str(candidate)
    return None


def available(kind: str) -> bool:
    return bool(mac_office_app(kind)) and bool(shutil.which("open")) and bool(shutil.which("osascript"))


def _applescript_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace('"', '\\"')


def export_pdf(source: Path, destination: Path, kind: str) -> None:
    """Export a Word document or Excel workbook to PDF using Office for Mac."""
    app = mac_office_app(kind)
    if sys.platform != "darwin" or not app or not shutil.which("open") or not shutil.which("osascript"):
        raise RuntimeError(f"Microsoft {kind.title()} for Mac is not available")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination_path = _applescript_path(destination)
    if kind == "word":
        target = "targetObject"
        active = "active document"
        save = f'save as {target} file name "{destination_path}" file format format PDF'
        close = f"close {target} saving no"
        application_name = "Microsoft Word"
    elif kind == "excel":
        target = "targetObject"
        active = "active workbook"
        save = f'save workbook as {target} filename "{destination_path}" file format PDF file format'
        close = f"close {target} saving no"
        application_name = "Microsoft Excel"
    else:
        raise ValueError(f"Unsupported macOS Office application: {kind}")
    script = f'''\
 tell application "{application_name}"
     set targetObject to missing value
     repeat 60 times
         try
             set targetObject to {active}
             if targetObject is not missing value then exit repeat
         on error
             set targetObject to missing value
         end try
         delay 0.5
     end repeat
     if targetObject is missing value then error "Microsoft Office did not open the source file"
     {save}
     {close}
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
        raise RuntimeError(f"Microsoft {kind.title()} for Mac could not open {source.name}. {detail}")
    result = subprocess.run(
        ["osascript", "-"],
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode or not destination.exists():
        detail = (result.stderr or result.stdout).strip()
        hint = "Allow the application running the GUI to control Microsoft Office in System Settings > Privacy & Security > Automation."
        raise RuntimeError(f"Microsoft {kind.title()} for Mac could not export {source.name} to PDF. {detail or hint}")
