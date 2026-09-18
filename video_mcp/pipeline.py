from __future__ import annotations

import json
import os
import shutil
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .azure_mcp import resolve_speech
from .cancellation import check_cancel
from .config import ProjectConfig, validate_project
from .llm import generate_content_draft
from .presentation import create_presentation_from_outline
from .render import build_video, prepare_review_audio, render_presentation_pdf
from .speech import synthesize_project_language
from .state import WorkflowState
from .subtitles import generate_subtitles
from .video_frames import extract_all_keyframes
from .vision import analyze_images


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def _combine_audio(source_dir: Path, target: Path, other_dir: Path, gap_seconds: float) -> None:
    en_files = sorted(source_dir.glob("slide-*.wav"))
    other_files = sorted(other_dir.glob("slide-*.wav"))
    if len(en_files) != len(other_files) or not en_files:
        raise ValueError("English and Mandarin slide audio counts do not match")
    chunks: list[bytes] = []
    params = None
    for en_path, other_path in zip(en_files, other_files):
        with wave.open(str(en_path), "rb") as en_audio, wave.open(str(other_path), "rb") as other_audio:
            if en_audio.getparams()[:3] != other_audio.getparams()[:3]:
                raise ValueError("English and Mandarin WAV formats do not match")
            params = en_audio.getparams()
            en_frames = en_audio.readframes(en_audio.getnframes())
            other_frames = other_audio.readframes(other_audio.getnframes())
            target_frames = max(len(en_frames), len(other_frames))
            silence = b"\0" * (target_frames - len(en_frames))
            gap_frames = round(gap_seconds * params.framerate * params.sampwidth * params.nchannels)
            chunks.append(en_frames + silence + b"\0" * gap_frames)
    with wave.open(str(target), "wb") as output:
        output.setnchannels(params.nchannels)
        output.setsampwidth(params.sampwidth)
        output.setframerate(params.framerate)
        output.writeframes(b"".join(chunks))


def _approved(root: Path, stage: str) -> bool:
    approvals = root / ".video-work" / "approvals.json"
    if not approvals.exists():
        return False
    return bool(json.loads(approvals.read_text(encoding="utf-8")).get(stage, {}).get("approved"))


def _load_existing_draft(path: Path) -> dict[str, Any]:
    draft = json.loads(path.read_text(encoding="utf-8"))
    for key in ("outline", "primary_narration", "secondary_narration"):
        if key not in draft:
            raise ValueError(f"External content draft is missing {key}")
    return draft


def build_project(config: ProjectConfig, stop_after: str | None = None, cancel_check: Callable[[], bool] | None = None) -> dict[str, Any]:
    check_cancel(cancel_check)
    errors = validate_project(config)
    if errors:
        raise ValueError("; ".join(errors))
    work = config.root / ".video-work"
    work.mkdir(parents=True, exist_ok=True)
    state = WorkflowState(config.root)
    state.update("resource_validation")
    check_cancel(cancel_check)
    generated_presentation = config.output_dir / "presentation.pptx"
    has_existing_presentation = config.presentation is not None
    presentation = config.presentation or work / "generated-presentation.pptx"
    state.update("azure_resource_discovery")
    vision_report = work / "vision-analysis.json"
    if config.vision.enabled and vision_report.exists():
        vision_results = json.loads(vision_report.read_text(encoding="utf-8"))
    else:
        # 如果项目中有视频文件且没有预存的 vision 分析结果，自动提取关键帧
        has_video = getattr(config, "video_files", ()) and config.vision.enabled
        if has_video:
            keyframe_dir = work / "_keyframes"
            extra_frames, truncated = extract_all_keyframes(
                config.video_files, keyframe_dir, max_keyframes=getattr(config.vision, "max_keyframes", 8)
            )
            if extra_frames:
                all_images = tuple(list(config.image_files) + extra_frames)
                from dataclasses import replace
                config_with_frames = replace(config, image_files=all_images)
                vision_results = analyze_images(config_with_frames, work)
                state.update("vision_analysis", image_count=len(vision_results), video_keyframes=len(extra_frames), video_truncated=truncated)
            else:
                vision_results = []
        else:
            vision_results = analyze_images(config, work) if config.vision.enabled else []
    if config.vision.enabled:
        state.update("vision_analysis", image_count=len(vision_results))
    image_assignments = {
        int(item["suggested_slide"]): Path(item["file"])
        for item in vision_results
        if str(item.get("suggested_slide", "")).isdigit() and int(item["suggested_slide"]) > 0
    }
    if config.vision.enabled and vision_results and not _approved(config.root, "vision") and os.getenv("VIDEO_MCP_APPROVE_VISION", "").lower() not in {"1", "true", "yes"}:
        raise PermissionError("Vision analysis created a draft but is not approved. Review .video-work/vision-analysis.json and set VIDEO_MCP_APPROVE_VISION=true.")
    primary_narration = config.narration_primary
    secondary_narration = config.narration_secondary
    state.update("content_draft")
    draft_path = work / "content-draft.json"
    if draft_path.exists():
        draft = _load_existing_draft(draft_path)
    else:
        draft = generate_content_draft(config, work)
    if not _approved(config.root, "draft") and os.getenv("VIDEO_MCP_APPROVE_DRAFT", "").lower() not in {"1", "true", "yes"}:
        raise PermissionError("LLM draft created but not approved. Review .video-work/content-draft.json and approve the Draft before building.")
    primary_narration = work / "narration-primary.json"
    secondary_narration = work / "narration-secondary.json"
    if not has_existing_presentation and not (presentation.exists() and _approved(config.root, "presentation")):
        check_cancel(cancel_check)
        create_presentation_from_outline(draft["outline"], presentation, config.name, list(config.image_files), image_assignments, template=config.presentation_template)
    if not has_existing_presentation:
        config.output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(presentation, generated_presentation)
        presentation = generated_presentation
    presentation_pdf = config.output_dir / "presentation.pdf"
    if not presentation_pdf.exists() or not _approved(config.root, "presentation"):
        presentation_pdf = render_presentation_pdf(presentation, config.output_dir, cancel_check)
    state.update("presentation_ready", presentation=str(presentation), pdf=str(presentation_pdf))
    if stop_after == "presentation":
        state.update("presentation_ready", status="completed", presentation=str(presentation), pdf=str(presentation_pdf))
        return {"project": config.name, "version": config.version, "presentation": str(presentation), "pdf": str(presentation_pdf)}
    if not _approved(config.root, "presentation") and os.getenv("VIDEO_MCP_APPROVE_PRESENTATION", "").lower() not in {"1", "true", "yes"}:
        raise PermissionError("PPT and PDF are ready but not approved. Review both artifacts and approve the presentation stage before speech generation.")
    speech_resource, speech_key, voice_catalog = resolve_speech(config)
    primary_manifest = work / "primary-manifest.json"
    secondary_manifest = work / "secondary-manifest.json"
    primary_audio = work / "primary.wav"
    secondary_audio = work / "secondary.wav"
    audio_ready = all((work / name).exists() for name in ("audio-primary", "audio-secondary", "primary-manifest.json", "secondary-manifest.json", "primary.wav", "secondary.wav"))
    if not audio_ready:
        state.update("speech_synthesis")
        primary = synthesize_project_language(primary_narration, work / "audio-primary", config.primary_voice, config.primary_language, speech_key, speech_resource.location, cancel_check)
        secondary = synthesize_project_language(secondary_narration, work / "audio-secondary", config.secondary_voice, config.secondary_language, speech_key, speech_resource.location, cancel_check)
        primary_manifest.write_text(json.dumps(primary, indent=2), encoding="utf-8")
        secondary_manifest.write_text(json.dumps(secondary, indent=2, ensure_ascii=False), encoding="utf-8")
        _combine_audio(work / "audio-primary", primary_audio, work / "audio-secondary", config.gap_seconds)
        _combine_audio(work / "audio-secondary", secondary_audio, work / "audio-primary", config.gap_seconds)
    actual_duration_seconds = max(_wav_duration(primary_audio), _wav_duration(secondary_audio))
    duration_warning = bool(
        config.target_duration_seconds
        and abs(actual_duration_seconds - config.target_duration_seconds) > max(10.0, config.target_duration_seconds * 0.2)
    )
    review_target_duration = None if duration_warning else config.target_duration_seconds
    check_cancel(cancel_check)
    review_primary_audio, review_secondary_audio, review_normalized = prepare_review_audio(primary_audio, secondary_audio, work, review_target_duration, cancel_check)
    subtitle_target_duration = review_target_duration if review_normalized else None
    state.update("subtitle_generation")
    subtitle_paths = generate_subtitles(
        primary_narration,
        secondary_narration,
        primary_manifest,
        secondary_manifest,
        config.output_dir,
        config.primary_language,
        config.secondary_language,
        subtitle_target_duration,
        config.gap_seconds,
    )
    state.update("audio_ready", subtitles=subtitle_paths, actual_duration_seconds=round(actual_duration_seconds, 2), target_duration_seconds=config.target_duration_seconds, duration_warning=duration_warning)
    if stop_after == "audio":
        state.update("audio_ready", status="completed", subtitles=subtitle_paths, actual_duration_seconds=round(actual_duration_seconds, 2), target_duration_seconds=config.target_duration_seconds, duration_warning=duration_warning)
        return {"project": config.name, "version": config.version, "audio": str(review_primary_audio), "subtitles": subtitle_paths, "actual_duration_seconds": round(actual_duration_seconds, 2), "duration_warning": duration_warning}
    # Audio and subtitles are automatically accepted after generation. The user
    # reviews them locally; only Vision, Draft, and PPT require explicit approval.
    state.update("video_rendering")
    video_ready = config.output_dir.exists() and any(config.output_dir.glob("*.mp4"))
    if video_ready:
        result = {"output_dir": str(config.output_dir)}
    else:
        result = build_video(
            presentation,
            primary_audio,
            secondary_audio,
            config.output_dir,
            config.gap_seconds,
            config.target_duration_seconds,
            config.primary_language,
            config.secondary_language,
            cancel_check,
        )
    video_files = {
        "primary": str(config.output_dir / "presentation-primary.mp4"),
        "secondary": str(config.output_dir / "presentation-secondary.mp4"),
        "dual_track": str(config.output_dir / "presentation-dual.mp4"),
    }
    state.update("video_ready", status="completed", output_dir=str(config.output_dir), video_files=video_files)
    state.update("completed", status="completed", output_dir=str(config.output_dir))
    result.update({"project": config.name, "version": config.version, "run_id": state.data["run_id"], "review_audio_primary": str(review_primary_audio), "review_audio_secondary": str(review_secondary_audio), "primary_manifest": str(primary_manifest), "secondary_manifest": str(secondary_manifest), "subtitles": subtitle_paths, "vision_items": len(vision_results), "speech_resource": speech_resource.name, "speech_region": speech_resource.location, "available_voices": len(voice_catalog)})
    return result


def inspect_project(config: ProjectConfig) -> dict[str, Any]:
    errors = validate_project(config)
    return {
        "name": config.name,
        "version": config.version,
        "root": str(config.root),
        "sources": {
            "presentation": str(config.presentation) if config.presentation else None,
            "content_files": [str(path) for path in config.content_files],
            "image_files": [str(path) for path in config.image_files],
            "table_files": [str(path) for path in config.table_files],
            "video_files": [str(path) for path in config.video_files],
            "audio_files": [str(path) for path in config.audio_files],
            "narration_primary": str(config.narration_primary),
            "narration_secondary": str(config.narration_secondary),
            "subtitles": str(config.subtitles) if config.subtitles else None,
        },
        "languages": {"primary": config.primary_language, "secondary": config.secondary_language},
        "voices": {"primary": config.primary_voice, "secondary": config.secondary_voice},
        "target_duration_seconds": config.target_duration_seconds,
        "valid": not errors,
        "errors": errors,
    }
