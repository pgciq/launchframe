from __future__ import annotations

import html
import json
import os
import random
import re
import time
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .cancellation import check_cancel


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def sentences(text: str, language: str) -> list[str]:
    pattern = r"(?<=[.!?])\s+" if language.lower().startswith("en") else r"(?<=[。！？.!?])\s*"
    return [part.strip() for part in re.split(pattern, text.strip()) if part.strip()]


def ssml(text: str, voice: str, language: str, rate: str) -> str:
    parts = sentences(text, language)
    body = "".join(f"{html.escape(part)}<break time=\"180ms\"/>" for part in parts)
    return (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xml:lang="{language}"><voice name="{html.escape(voice)}">'
        f'<prosody rate="{html.escape(rate)}">{body}</prosody></voice></speak>'
    )


def _message(result: Any) -> str:
    details = getattr(result, "cancellation_details", None)
    if not details:
        return str(getattr(result, "reason", "unknown"))
    return " ".join(str(getattr(details, key, "")) for key in ("reason", "error_code", "error_details"))


def sentence_timings(events: list[dict[str, Any]], text: str, language: str) -> list[dict[str, float]] | None:
    parts = sentences(text, language)
    candidates = [(index, event) for index, event in enumerate(events) if str(event.get("text", "")) in ".?!。！？"]
    if not parts or not events or len(candidates) < len(parts):
        return None
    used: set[int] = set()
    terminals: list[int] = []
    search_start = 0
    base_offset = int(events[0].get("text_offset", 0))
    for part in parts:
        position = text.find(part, search_start)
        if position < 0:
            return None
        expected = base_offset + position + len(part) - 1
        match = min(((abs(int(event.get("text_offset", 0)) - expected), index) for index, event in candidates if index not in used), default=(999999, -1))[1]
        if match < 0:
            return None
        used.add(match)
        terminals.append(match)
        search_start = position + len(part)
    starts = [float(events[0].get("audio_offset", 0)) / 10_000_000]
    starts.extend(float(events[index + 1].get("audio_offset", 0)) / 10_000_000 for index in terminals[:-1])
    return [{"start_seconds": round(start, 4), "end_seconds": round(float(events[index].get("audio_offset", 0)) / 10_000_000 + float(events[index].get("duration_seconds", 0)), 4)} for start, index in zip(starts, terminals)]


def synthesize_voice_preview(text: str, voice: str, language: str, speech_key: str, speech_region: str, output_path: Path) -> Path:
    """Synthesize a short voice preview without creating project narration artifacts."""
    import azure.cognitiveservices.speech as speechsdk

    if not text.strip():
        raise ValueError("Preview text must not be empty")
    if not voice.strip() or not language.strip():
        raise ValueError("A language and voice are required for preview")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    config.speech_synthesis_voice_name = voice
    config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
    audio_config = speechsdk.audio.AudioOutputConfig(filename=str(output_path))
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=audio_config)
    result = synthesizer.speak_text_async(text.strip()).get()
    if result.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
        raise RuntimeError(f"Voice preview synthesis failed: {_message(result)}")
    return output_path


def synthesize_project_language(
    narration_path: Path,
    output_dir: Path,
    voice: str,
    language: str,
    speech_key: str | None = None,
    speech_region: str | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    import azure.cognitiveservices.speech as speechsdk

    key = speech_key or required_env("AZURE_SPEECH_KEY")
    region = speech_region or required_env("AZURE_SPEECH_REGION")
    rate = os.getenv("AZURE_SPEECH_RATE", "0%")
    interval = float(os.getenv("AZURE_SPEECH_MIN_REQUEST_INTERVAL_SECONDS", "3.2"))
    retries = max(0, int(os.getenv("AZURE_SPEECH_MAX_RETRIES", "5")))
    retry_base = float(os.getenv("AZURE_SPEECH_RETRY_BASE_SECONDS", "4"))
    config = speechsdk.SpeechConfig(subscription=key, region=region)
    config.speech_synthesis_voice_name = voice
    config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm)
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=config, audio_config=None)
    raw_items = json.loads(narration_path.read_text(encoding="utf-8"))
    items = []
    for index, item in enumerate(raw_items):
        if isinstance(item, str):
            items.append({"slide": index + 1, "text": item})
        elif isinstance(item, dict):
            normalized = dict(item)
            normalized.setdefault("slide", index + 1)
            if "text" not in normalized:
                raise ValueError(f"Narration item {index + 1} is missing text: {narration_path}")
            items.append(normalized)
        else:
            raise TypeError(f"Narration item {index + 1} must be an object or string: {narration_path}")
    narration_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_items = []
    last_request = 0.0

    for item in items:
        check_cancel(cancel_check)
        slide = int(item["slide"])
        events: list[dict[str, Any]] = []

        def boundary(event, event_list=events) -> None:
            event_list.append({
                "audio_offset": event.audio_offset,
                "duration_seconds": event.duration.total_seconds(),
                "text": event.text,
                "text_offset": event.text_offset,
                "word_length": event.word_length,
            })

        synthesizer.synthesis_word_boundary.connect(boundary)
        for attempt in range(retries + 1):
            wait = interval - (time.monotonic() - last_request)
            if wait > 0:
                time.sleep(wait)
            last_request = time.monotonic()
            try:
                result = synthesizer.speak_ssml_async(ssml(item["text"], voice, language, rate)).get()
                check_cancel(cancel_check)
                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    break
                message = _message(result)
            except Exception as exc:  # noqa: BLE001 - SDK exception classes differ by platform.
                message = str(exc)
            if attempt >= retries:
                raise RuntimeError(f"Speech failed for slide {slide}: {message}")
            time.sleep(retry_base * (2**attempt) + random.uniform(0, 1))
        synthesizer.synthesis_word_boundary.disconnect(boundary) if hasattr(synthesizer.synthesis_word_boundary, "disconnect") else None

        output = output_dir / f"slide-{slide:02d}.wav"
        output.write_bytes(result.audio_data)
        with wave.open(str(output), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
        manifest_items.append({
            "slide": slide,
            "title": item.get("title", f"Slide {slide}"),
            "audio": output.name,
            "duration_seconds": round(duration, 3),
            "word_boundaries": events,
            "sentence_timings": sentence_timings(events, item["text"], language),
        })

    return {"voice": voice, "language": language, "slides": manifest_items}
