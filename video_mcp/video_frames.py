"""从视频文件自动提取关键帧，供 Vision API 分析使用。"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
FRAME_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _get_ffmpeg() -> str | None:
    for candidate in (
        shutil.which("ffmpeg"),
        shutil.which("ffmpeg.exe"),
    ):
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    return None


def _get_video_duration(video: Path, ffmpeg: str) -> float:
    result = subprocess.run(
        [ffmpeg, "-i", str(video)],
        capture_output=True, text=True, timeout=30
    )
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
    if m:
        h, mi, s = m.groups()
        return int(h) * 3600 + int(mi) * 60 + float(s)
    return 0.0


def extract_keyframes(
    video: Path,
    output_dir: Path,
    max_frames: int = 8,
    ffmpeg: str | None = None,
) -> list[Path]:
    """从单个视频均匀提取最多 max_frames 帧。

    策略：
      - 视频 ≤ max_frames 秒：每秒一帧（不超过 max_frames）
      - 视频 > max_frames 秒：均匀分布，首帧 + 尾帧 + 中间均匀采样
    """
    ff = ffmpeg or _get_ffmpeg()
    if ff is None:
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    duration = _get_video_duration(video, ff)
    if duration <= 0:
        return []

    # 计算采样时间点
    if max_frames <= 1:
        # 只需一帧：取视频中间点（比首帧更可靠）
        times = [round(duration / 2, 2)] if duration > 0 else [0.0]
    elif duration <= max_frames:
        times = [round(i, 2) for i in range(0, int(duration) + 1)]
    else:
        # 首帧 + 尾帧 + 中间均匀分布
        step = duration / (max_frames - 1)
        times = [round(i * step, 2) for i in range(max_frames)]
        # 确保首尾
        if abs(times[0]) > 0.01:
            times[0] = 0.0
        if times[-1] < duration - 0.1:
            times[-1] = round(duration * 0.99, 2)
        times = sorted({round(t, 3) for t in times})[:max_frames]

    frames: list[Path] = []
    for i, t in enumerate(times):
        out = output_dir / f"keyframe_{video.stem}_{i+1:03d}.jpg"
        # -ss 前置到 -i 前面（快速seek），对首帧(t=0)改用后置方式确保准确
        if t == 0.0:
            cmd = [
                ff, "-y", "-i", str(video),
                "-ss", "0.0",
                "-vframes", "1",
                "-vf", "scale=640:-1",
                "-q:v", "2",
                str(out),
            ]
        else:
            cmd = [
                ff, "-y", "-ss", f"{t:.3f}",
                "-i", str(video),
                "-vframes", "1",
                "-vf", "scale=640:-1",
                "-q:v", "2",
                str(out),
            ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 100:
            frames.append(out)

    return frames


def extract_all_keyframes(
    videos: tuple[Path, ...],
    work_dir: Path,
    max_keyframes: int = 8,
    ffmpeg: str | None = None,
) -> tuple[list[Path], int]:
    """为所有视频文件提取关键帧，返回 (帧路径列表, 被截断的视频数)。

    总帧数上限 = max_keyframes，超出时保留时长最长视频的帧，其余截断。
    """
    ff = ffmpeg or _get_ffmpeg()
    if ff is None:
        return [], 0

    all_frames: list[Path] = []
    truncated_count = 0
    budget = max_keyframes

    # 按视频时长降序排列，优先保留长视频的帧
    video_durations = [
        (v, _get_video_duration(v, ffmpeg))
        for v in videos
        if v.suffix.lower() in VIDEO_EXTENSIONS and v.exists()
    ]
    video_durations.sort(key=lambda x: x[1], reverse=True)

    for video, _ in video_durations:
        if budget <= 0:
            truncated_count += 1
            continue
        keyframe_dir = work_dir / "_keyframes" / video.stem
        frames = extract_keyframes(video, keyframe_dir, max_frames=budget, ffmpeg=ffmpeg)
        all_frames.extend(frames)
        truncated = budget - len(frames)
        if truncated < 0:
            truncated_count += 1
        budget = max(0, budget - len(frames))

    return all_frames, truncated_count
