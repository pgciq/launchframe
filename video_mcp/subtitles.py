from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _is_cjk_heavy(text: str) -> bool:
    """Return True if CJK characters account for >= 20% of non-whitespace chars."""
    stripped = text.replace("\n", " ").replace("\r", " ").strip()
    if not stripped:
        return False
    cjk_count = sum(1 for c in stripped if "\u4e00" <= c <= "\u9fff" or
                    "\u3040" <= c <= "\u30ff" or  # Hiragana/Katakana
                    "\u3400" <= c <= "\u4dbf")    # CJK Extension A
    return cjk_count >= len(stripped) // 5


def _detect_language(text: str) -> str:
    """Auto-detect language from text: 'zh-CN' for CJK-heavy, 'en-US' otherwise."""
    return "zh-CN" if _is_cjk_heavy(text) else "en-US"


def split_sentences(text: str, language: str | None = None) -> list[str]:
    """Split text into sentences, using paragraph boundaries (\\n) as implicit sentence delimiters.

    When *language* is not provided, it is auto-detected from the text.
    Paragraph boundaries ensure each visual block stays as a separate cue,
    even if the block contains no terminal punctuation.
    """
    # Auto-detect language if not given
    if language is None:
        language = _detect_language(text)

    # Normalize: treat paragraph breaks as sentence separators
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    # Split on paragraph boundaries first
    paragraphs = [p.strip() for p in normalized.split("\n") if p.strip()]

    if not paragraphs:
        return []

    pattern = (r"(?<=[.!?])\s+" if language.lower().startswith("en")
               else r"(?<=[。！？.!?])\s*")

    result: list[str] = []
    for para in paragraphs:
        parts = re.split(pattern, para)
        for part in parts:
            part = part.strip()
            if part:
                result.append(part)

    return result


MAX_LATIN_LINE_CHARS = 56
MAX_CJK_LINE_CHARS = 24
MAX_LINES_PER_CUE = 2


def _find_break(text: str, start: int, line_limit: int, is_cjk: bool) -> int:
    """Find the best break point in *text[start:]* that keeps the first line ≤ line_limit.

    Returns the absolute index of the break.  If no natural boundary exists within
    the limit, returns ``start + line_limit`` (hard cut).
    """
    window = text[start:]
    if is_cjk:
        # CJK: prefer punctuation within the window; if none within limit, hard-cut
        puncts = "，,、；;：:"
        candidates = [start + i + 1 for i, c in enumerate(window) if c in puncts]
        within_limit = [p for p in candidates if p - start <= line_limit]
        if within_limit:
            # Pick the one closest to the midpoint of the window (visually balanced)
            mid = start + len(window) // 2
            return min(within_limit, key=lambda p: abs(p - mid))
        # No punctuation within limit — hard cut at line_limit
        return min(start + line_limit, len(text))
    else:
        # Latin: prefer space within the window; if none within limit, hard-cut
        spaces = [start + i + 1 for i, c in enumerate(window[:-1]) if c == " "]
        within_limit = [p for p in spaces if p - start <= line_limit]
        if within_limit:
            mid = start + len(window) // 2
            return min(within_limit, key=lambda p: abs(p - mid))
        return min(start + line_limit, len(text))


def _wrap_lines(text: str, line_limit: int, is_cjk: bool) -> str:
    """Wrap *text* into lines, each ≤ line_limit characters.

    Unlike a simple two-line split, this recursively wraps long text by finding
    the best natural boundary in each segment.  The result is a single string
    with ``\\n`` between lines.
    """
    if len(text) <= line_limit:
        return text
    parts: list[str] = []
    pos = 0
    while pos < len(text):
        remaining = text[pos:]
        if len(remaining) <= line_limit:
            parts.append(remaining)
            break
        cut = _find_break(text, pos, line_limit, is_cjk)
        parts.append(text[pos:cut].rstrip())
        pos = cut
    return "\n".join(parts)


def _as_cue(text: str, line_limit: int, is_cjk: bool) -> str:
    """Format *text* as a subtitle cue (lines each ≤ line_limit).

    Sentences that fit within *line_limit* characters are returned unchanged.
    Longer text is wrapped recursively so no line exceeds the limit.
    """
    if len(text) <= line_limit:
        return text
    return _wrap_lines(text, line_limit, is_cjk)


def split_display_chunks(text: str, language: str | None = None) -> list[str]:
    """Split text into subtitle cue(s) with at most two visual lines each.

    Sentences short enough to fit within two display lines are kept as a
    single cue so the viewer reads a complete thought at once rather than a
    stream of short fragments.  Only text longer than two lines produces
    multiple sequential cues.

    When *language* is not provided, it is auto-detected from the text
    using a CJK character ratio heuristic (>= 20% CJK = Chinese language).
    """
    remaining = text.strip()
    if not remaining:
        return []
    # Use explicit language arg if provided, otherwise auto-detect
    lang = language if language is not None else _detect_language(remaining)
    is_cjk = lang.lower().startswith(("zh", "ja", "ko"))
    line_limit = MAX_CJK_LINE_CHARS if is_cjk else MAX_LATIN_LINE_CHARS
    cue_limit = line_limit * MAX_LINES_PER_CUE

    chunks: list[str] = []
    while len(remaining) > cue_limit:
        # Find the best natural break point within the cue_limit window
        cut = _find_break(remaining, 0, cue_limit, is_cjk)
        chunks.append(_as_cue(remaining[:cut].rstrip(), line_limit, is_cjk))
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(_as_cue(remaining, line_limit, is_cjk))
    return chunks


def _split_bilingual_chunks(text: str) -> list[str]:
    lines = text.splitlines()
    if len(lines) < 2:
        return split_display_chunks(text, "en-US")
    primary_chunks = split_display_chunks(lines[0], "en-US")
    secondary_chunks = split_display_chunks(lines[1], "zh-CN")
    count = max(len(primary_chunks), len(secondary_chunks))
    return [
        "\n".join(
            part for part in (
                primary_chunks[index] if index < len(primary_chunks) else "",
                secondary_chunks[index] if index < len(secondary_chunks) else "",
            ) if part
        )
        for index in range(count)
    ]


def split_timed_cues(cues: list[tuple[float, float, str]], language: str, bilingual: bool = False) -> list[tuple[float, float, str]]:
    """Split oversized cues while proportionally preserving their timings."""
    result: list[tuple[float, float, str]] = []
    for start, end, text in cues:
        chunks = _split_bilingual_chunks(text) if bilingual else split_display_chunks(text, language)
        if len(chunks) <= 1:
            result.append((start, end, text))
            continue
        weights = [max(1, len(chunk.replace("\n", ""))) for chunk in chunks]
        total = sum(weights)
        current = start
        duration = max(0.0, end - start)
        for index, (chunk, weight) in enumerate(zip(chunks, weights)):
            chunk_end = end if index == len(chunks) - 1 else current + duration * weight / total
            result.append((current, chunk_end, chunk))
            current = chunk_end
    return result


def timestamp(seconds: float, vtt: bool = False) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_value, milliseconds = divmod(remainder, 1_000)
    separator = "." if vtt else ","
    return f"{hours:02d}:{minutes:02d}:{seconds_value:02d}{separator}{milliseconds:03d}"


def timings(text: str, language: str, slide: dict[str, Any]) -> list[dict[str, float]]:
    sentences = split_sentences(text, language)
    events = slide.get("word_boundaries", [])
    candidates = [
        (index, event)
        for index, event in enumerate(events)
        if event.get("text", "") in ".?!。！？"
    ]
    if not candidates or not events:
        duration = float(slide["duration_seconds"])
        share = duration / max(1, len(sentences))
        return [{"start": index * share, "end": (index + 1) * share} for index in range(len(sentences))]

    base_offset = int(events[0]["text_offset"])
    used: set[int] = set()
    terminal: list[int] = []
    search_start = 0
    for sentence in sentences:
        position = text.find(sentence, search_start)
        if position < 0:
            raise ValueError(f"Cannot locate sentence in narration: {sentence}")
        expected = base_offset + position + len(sentence) - 1
        match = min(
            ((abs(int(event["text_offset"]) - expected), index) for index, event in candidates if index not in used),
            default=(999999, -1),
        )[1]
        if match < 0:
            raise ValueError("Cannot match Speech word boundary to a sentence")
        used.add(match)
        terminal.append(match)
        search_start = position + len(sentence)

    starts = [float(events[0]["audio_offset"]) / 10_000_000]
    starts.extend(float(events[index + 1]["audio_offset"]) / 10_000_000 for index in terminal[:-1])
    return [
        {
            "start": start,
            "end": float(events[index]["audio_offset"]) / 10_000_000 + float(events[index].get("duration_seconds", 0)),
        }
        for start, index in zip(starts, terminal)
    ]


def proportional_timings(text: str, language: str, duration: float) -> list[dict[str, float]]:
    parts = split_sentences(text, language)
    if not parts:
        return []
    weights = [max(1, len(part)) for part in parts]
    total = sum(weights)
    current = 0.0
    result = []
    for weight in weights:
        end = current + duration * weight / total
        result.append({"start": current, "end": end})
        current = end
    return result


def write_srt(path: Path, cues: list[tuple[float, float, str]]) -> None:
    blocks = []
    for index, (start, end, text) in enumerate(cues, 1):
        blocks.extend([str(index), f"{timestamp(start)} --> {timestamp(end)}", text, ""])
    path.write_text("\n".join(blocks), encoding="utf-8")


def write_vtt(path: Path, cues: list[tuple[float, float, str]]) -> None:
    blocks = ["WEBVTT", ""]
    for index, (start, end, text) in enumerate(cues, 1):
        blocks.extend([str(index), f"{timestamp(start, True)} --> {timestamp(end, True)}", text, ""])
    path.write_text("\n".join(blocks), encoding="utf-8")


def generate_subtitles(
    primary_narration: Path,
    secondary_narration: Path,
    primary_manifest: Path,
    secondary_manifest: Path,
    output_dir: Path,
    primary_language: str,
    secondary_language: str,
    target_duration_seconds: float | None = None,
    gap_seconds: float = 0.0,
) -> dict[str, str]:
    primary = {int(item["slide"]): item for item in json.loads(primary_narration.read_text(encoding="utf-8"))}
    secondary = {int(item["slide"]): item for item in json.loads(secondary_narration.read_text(encoding="utf-8"))}
    primary_data = {int(item["slide"]): item for item in json.loads(primary_manifest.read_text(encoding="utf-8"))["slides"]}
    secondary_data = {int(item["slide"]): item for item in json.loads(secondary_manifest.read_text(encoding="utf-8"))["slides"]}
    output_dir.mkdir(parents=True, exist_ok=True)
    slide_duration_total = sum(
        max(float(primary_data[slide]["duration_seconds"]), float(secondary_data[slide]["duration_seconds"])) + gap_seconds
        for slide in primary
    )
    # A longer target duration is implemented as silence padding, not by
    # slowing speech. Only compress timings when the target is shorter.
    scale = min(1.0, target_duration_seconds / slide_duration_total) if target_duration_seconds else 1.0
    primary_cues: list[tuple[float, float, str]] = []
    secondary_cues: list[tuple[float, float, str]] = []
    bilingual_cues: list[tuple[float, float, str]] = []
    timeline = 0.0

    for slide in sorted(primary):
        p_sentences = split_sentences(primary[slide]["text"], primary_language)
        s_sentences = split_sentences(secondary[slide]["text"], secondary_language)
        if len(p_sentences) != len(s_sentences):
            # Translations do not always preserve sentence boundaries. Keep
            # the slide synchronized with one full-slide cue instead of
            # failing the entire audio stage.
            p_duration = float(primary_data[slide]["duration_seconds"]) * scale
            s_duration = float(secondary_data[slide]["duration_seconds"]) * scale
            primary_cues.append((timeline, timeline + p_duration, primary[slide]["text"]))
            secondary_cues.append((timeline, timeline + s_duration, secondary[slide]["text"]))
            bilingual_cues.append((timeline, timeline + max(p_duration, s_duration), f"{primary[slide]['text']}\n{secondary[slide]['text']}"))
            timeline += max(p_duration, s_duration)
            continue
        p_raw_times = primary_data[slide].get("sentence_timings")
        s_raw_times = secondary_data[slide].get("sentence_timings")
        p_times = ([{"start": float(item["start_seconds"]) * scale, "end": float(item["end_seconds"]) * scale} for item in p_raw_times] if p_raw_times and len(p_raw_times) == len(p_sentences) else proportional_timings(primary[slide]["text"], primary_language, float(primary_data[slide]["duration_seconds"]) * scale))
        s_times = ([{"start": float(item["start_seconds"]) * scale, "end": float(item["end_seconds"]) * scale} for item in s_raw_times] if s_raw_times and len(s_raw_times) == len(s_sentences) else proportional_timings(secondary[slide]["text"], secondary_language, float(secondary_data[slide]["duration_seconds"]) * scale))
        for index, (p_text, s_text) in enumerate(zip(p_sentences, s_sentences)):
            p_start = timeline + p_times[index]["start"]
            p_end = timeline + p_times[index]["end"]
            s_start = timeline + s_times[index]["start"]
            s_end = timeline + s_times[index]["end"]
            primary_cues.append((p_start, p_end, p_text))
            secondary_cues.append((s_start, s_end, s_text))
            bilingual_cues.append((min(p_start, s_start), max(p_end, s_end), f"{p_text}\n{s_text}"))
        timeline += (max(float(primary_data[slide]["duration_seconds"]), float(secondary_data[slide]["duration_seconds"])) + gap_seconds) * scale

    primary_cues = split_timed_cues(primary_cues, primary_language)
    secondary_cues = split_timed_cues(secondary_cues, secondary_language)
    bilingual_cues = split_timed_cues(bilingual_cues, primary_language, bilingual=True)
    paths = {
        "primary_srt": output_dir / "presentation-primary.srt",
        "secondary_srt": output_dir / "presentation-secondary.srt",
        "bilingual_srt": output_dir / "presentation-bilingual.srt",
        "primary_vtt": output_dir / "presentation-primary.vtt",
        "secondary_vtt": output_dir / "presentation-secondary.vtt",
        "bilingual_vtt": output_dir / "presentation-bilingual.vtt",
    }
    write_srt(paths["primary_srt"], primary_cues)
    write_srt(paths["secondary_srt"], secondary_cues)
    write_srt(paths["bilingual_srt"], bilingual_cues)
    write_vtt(paths["primary_vtt"], primary_cues)
    write_vtt(paths["secondary_vtt"], secondary_cues)
    write_vtt(paths["bilingual_vtt"], bilingual_cues)
    return {key: str(path) for key, path in paths.items()}
