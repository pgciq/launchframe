from __future__ import annotations

import contextlib
import csv
import json
import re
import subprocess
import zipfile
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

_SUBTITLE_TIMESTAMP_RE = re.compile(
    r"""
    \d{1,2}:\d{2}:\d{2}[,.]\d+   # SRT full: 00:00:00,000  or  00:00:00.000
    |\d{1,2}:\d{2}\.\d+             # VTT short: 00:00.000
    """,
    re.VERBOSE,
)
_SUBTITLE_ARROW_RE = re.compile(r"\d{1,2}:\d{2}(?:[:.,]\d+)?\s*-->\s*\d{1,2}:\d{2}(?:[:.,]\d+)?")
_SRT_SEQ_RE = re.compile(r"^\d+$")

BLUE = RGBColor(37, 99, 235)
DARK = RGBColor(15, 23, 42)
MUTED = RGBColor(71, 85, 105)


def _open_template(template: str | Path) -> Presentation:
    """Open a .pptx file as a visual template: remove all content slides,
    preserve slide masters / theme / layouts."""
    prs = Presentation(str(template))
    sldIdLst = prs.slides._sldIdLst
    for sld_id in list(sldIdLst):
        rId = sld_id.get(qn("r:id"))
        with contextlib.suppress(Exception):
            prs.part.drop_rel(rId)
        sldIdLst.remove(sld_id)
    return prs


def _pick_layout(prs: Presentation, preferred: tuple[str, ...], fallback: int = 1):
    """Return the first layout whose name contains any preferred substring (case-insensitive)."""
    for layout in prs.slide_layouts:
        name_lower = (layout.name or "").lower()
        if any(p.lower() in name_lower for p in preferred):
            return layout
    idx = min(fallback, len(prs.slide_layouts) - 1)
    return prs.slide_layouts[idx]


def _decode(raw: bytes) -> str:
    """Decode bytes trying UTF-8, then cp1252, then latin-1 as last resort."""
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", errors="replace")


def _read_text(path: Path) -> str:
    return _decode(path.read_bytes())


def _read_document(path: Path) -> str:
    if path.suffix.lower() in {".md", ".txt", ".rst"}:
        return _read_text(path)
    if path.suffix.lower() == ".json":
        return json.dumps(json.loads(_read_text(path)), ensure_ascii=False, indent=2)
    if path.suffix.lower() in {".yaml", ".yml"}:
        import yaml
        return json.dumps(yaml.safe_load(_read_text(path)), ensure_ascii=False, indent=2)
    if path.suffix.lower() == ".xml":
        return "\n".join(ET.fromstring(_read_text(path)).itertext())
    if path.suffix.lower() == ".csv":
        import io
        with io.StringIO(_read_text(path)) as csv_file:
            return "\n".join(" | ".join(row) for row in csv.reader(csv_file))
    if path.suffix.lower() == ".xlsx":
        from openpyxl import load_workbook
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            return "\n".join(" | ".join(str(value or "") for value in row) for sheet in workbook.worksheets for row in sheet.iter_rows(values_only=True))
        finally:
            workbook.close()
    if path.suffix.lower() == ".eml":
        from email import policy
        from email.parser import BytesParser
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        lines = [
            f"Subject: {message.get('subject', '')}",
            f"From: {message.get('from', '')}",
            f"To: {message.get('to', '')}",
            f"Date: {message.get('date', '')}",
            "",
        ]
        if message.is_multipart():
            for part in message.walk():
                if part.get_content_type() == "text/plain" and not part.get_filename():
                    lines.append(part.get_content())
        elif message.get_content_type() == "text/plain":
            lines.append(message.get_content())
        else:
            lines.append(message.get_body(preferencelist=("plain", "html")).get_content() if message.get_body() else "")
        attachments = [part.get_filename() for part in message.iter_attachments() if part.get_filename()]
        if attachments:
            lines.extend(["", "Attachments: " + ", ".join(attachments)])
        return "\n".join(lines).strip()
    if path.suffix.lower() == ".one":
        # .one is a proprietary binary format. Extract readable text when the
        # macOS/Windows OneNote application is unavailable; visual analysis is
        # best handled by exporting the page to PDF first.
        try:
            result = subprocess.run(["strings", "-a", str(path)], capture_output=True, text=True, check=False)
            text = "\n".join(line.strip() for line in result.stdout.splitlines() if line.strip())
        except FileNotFoundError:
            text = ""
        return text or f"OneNote page: {path.name} (export to PDF for visual analysis)"
    if path.suffix.lower() == ".vsdx":
        lines: list[str] = []
        with zipfile.ZipFile(path) as package:
            for name in package.namelist():
                if name.startswith("visio/pages/") and name.endswith(".xml"):
                    root = ET.fromstring(package.read(name))
                    lines.extend(text.strip() for text in root.itertext() if text.strip())
        return "\n".join(lines) or f"Visio diagram: {path.name}"
    if path.suffix.lower() in {".doc", ".xls", ".numbers", ".pages", ".key", ".vsd"}:
        return f"Office document: {path.name}. Use the rendered Vision pages for visual content."
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if path.suffix.lower() in {".docx", ".doc"}:
        from docx import Document
        return "\n".join(paragraph.text for paragraph in Document(str(path)).paragraphs)
    if path.suffix.lower() in {".srt", ".vtt"}:
        return _read_subtitle(path)
    if path.suffix.lower() in {".pptx", ".ppt"}:
        from pptx import Presentation as _Prs
        from pptx.util import Pt as _Pt  # noqa: F401 — ensure pptx is importable
        prs = _Prs(str(path))
        lines: list[str] = []
        for i, slide in enumerate(prs.slides, 1):
            slide_lines: list[str] = [f"--- Slide {i} ---"]
            for shape in slide.shapes:
                if not shape.has_text_frame:
                    continue
                for para in shape.text_frame.paragraphs:
                    text = para.text.strip()
                    if text:
                        slide_lines.append(text)
            if slide.has_notes_slide:
                notes_text = slide.notes_slide.notes_text_frame.text.strip()
                if notes_text:
                    slide_lines.append(f"[Notes] {notes_text}")
            lines.extend(slide_lines)
        return "\n".join(lines)
    raise ValueError(f"Unsupported content document: {path}")


def _read_subtitle(path: Path) -> str:
    """Extract plain narration text from an SRT or VTT subtitle file."""
    text = _read_text(path)
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.upper().startswith(("WEBVTT", "NOTE ", "STYLE", "REGION")):
            continue
        # Match both SRT (00:00:00,000 --> 00:00:04,500) and VTT (00:00.000 --> 00:04.500)
        if _SUBTITLE_TIMESTAMP_RE.match(stripped) or _SUBTITLE_ARROW_RE.match(stripped):
            continue
        if _SRT_SEQ_RE.match(stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _content_lines(paths: Iterable[Path]) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    title = "Product presentation"
    bullets: list[str] = []
    for path in paths:
        for raw in _read_document(path).splitlines():
            line = raw.strip()
            if not line:
                continue
            heading = re.match(r"^#{1,3}\s+(.+)$", line)
            if heading:
                if bullets:
                    sections.append((title, bullets))
                    bullets = []
                title = heading.group(1).strip()
            elif line.startswith(('-', '*')):
                bullets.append(line[1:].strip())
            else:
                bullets.append(line)
    if bullets:
        sections.append((title, bullets))
    return sections or [(title, ["Product overview"])]


def _add_text(slide, text: str, x: float, y: float, w: float, h: float, size: int, color: RGBColor, bold: bool = False) -> None:
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    frame = box.text_frame
    frame.word_wrap = True
    frame.clear()
    paragraph = frame.paragraphs[0]
    run = paragraph.add_run()
    run.text = text
    run.font.name = "Aptos"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def create_presentation_from_outline(outline: list[dict], output: Path, project_name: str, image_files: list[Path] | None = None, image_assignments: dict[int, Path] | None = None, template: str | Path | None = None) -> Path:
    sections: list[tuple[str, list[str]]] = []
    for index, item in enumerate(outline):
        if isinstance(item, str):
            sections.append((item, [item]))
            continue
        if not isinstance(item, dict):
            raise TypeError(f"outline item {index + 1} must be an object or string")
        title = str(item.get("title", f"Slide {index + 1}"))
        points = item.get("key_points") or item.get("text") or item.get("body") or []
        if isinstance(points, str):
            points = [points]
        sections.append((title, [str(point) for point in points]))
    return _create_sections(sections, output, project_name, image_files, image_assignments, template=template)


def create_presentation(content_files: list[Path], output: Path, project_name: str, image_files: list[Path] | None = None, image_assignments: dict[int, Path] | None = None, template: str | Path | None = None) -> Path:
    return _create_sections(_content_lines(content_files), output, project_name, image_files, image_assignments, template=template)


def _create_sections(sections: list[tuple[str, list[str]]], output: Path, project_name: str, image_files: list[Path] | None = None, image_assignments: dict[int, Path] | None = None, template: str | Path | None = None) -> Path:
    using_template = template and Path(template).exists()
    if using_template:
        try:
            presentation = _open_template(Path(template))  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001
            using_template = False
            presentation = Presentation()
    if not using_template:
        presentation = Presentation()
        presentation.slide_width = Inches(13.333)
        presentation.slide_height = Inches(7.5)
    for index, (title, bullets) in enumerate(sections):
        if using_template:
            # Use template layouts by name; title slide uses "title" layout
            layout = _pick_layout(presentation, ("title slide", "title") if index == 0 else ("title and content", "content", "blank"), fallback=0 if index == 0 else 1)
            slide = presentation.slides.add_slide(layout)
            # Find the first title placeholder and set text
            for ph in slide.placeholders:
                if ph.placeholder_format.idx == 0:  # title
                    ph.text = project_name if index == 0 else title
                    break
            else:
                _add_text(slide, project_name if index == 0 else title, 0.75, 0.35, 11.8, 0.9, 28 if index == 0 else 24, RGBColor(248, 250, 252), True)
            if index == 0:
                for ph in slide.placeholders:
                    if ph.placeholder_format.idx in {1, 2}:  # subtitle / content
                        ph.text = title
                        break
                else:
                    _add_text(slide, title, 0.78, 1.4, 11.5, 0.5, 18, RGBColor(203, 213, 225))
            else:
                # Find content placeholder (idx != 0)
                content_ph = next((ph for ph in slide.placeholders if ph.placeholder_format.idx != 0), None)
                if content_ph is not None:
                    tf = content_ph.text_frame
                    tf.clear()
                    for b_idx, bullet in enumerate(bullets[:8]):
                        p = tf.paragraphs[0] if b_idx == 0 else tf.add_paragraph()
                        p.text = bullet
                else:
                    for bullet_index, bullet in enumerate(bullets[:8]):
                        _add_text(slide, f"• {bullet}", 1.0, 1.8 + bullet_index * 0.52, 11.0, 0.4, 16, RGBColor(226, 232, 240))
        else:
            slide = presentation.slides.add_slide(presentation.slide_layouts[6])
            background = slide.background.fill
            background.solid()
            background.fore_color.rgb = DARK
            _add_text(slide, project_name if index == 0 else title, 0.75, 0.65, 11.8, 0.8, 30 if index == 0 else 25, BLUE if index == 0 else RGBColor(248, 250, 252), True)
            if index == 0:
                _add_text(slide, title, 0.78, 1.65, 11.5, 0.45, 18, RGBColor(203, 213, 225))
            for bullet_index, bullet in enumerate(bullets[:8]):
                _add_text(slide, f"• {bullet}", 1.0, 2.1 + bullet_index * 0.52, 8.0 if image_files else 11.0, 0.4, 16, RGBColor(226, 232, 240))
            _add_text(slide, f"{index + 1:02d} / {len(sections):02d}", 11.75, 7.05, 0.9, 0.2, 8, MUTED)
        # Always try to add the image if available
        image = image_assignments.get(index + 1) if image_assignments else None
        if image is None and image_files and index < len(image_files):
            image = image_files[index]
        if image is not None:
            with contextlib.suppress(Exception):
                slide.shapes.add_picture(str(image), Inches(9.4), Inches(1.8), width=Inches(3.2))
    output.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(output)
    return output
