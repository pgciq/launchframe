#!/usr/bin/env python3
"""
视频关键帧提取工具

功能：
  1. 从视频文件提取关键帧（等间隔 / 场景变化 / 指定时间点）
  2. 自动送入 Vision API 分析，生成 slide 推荐
  3. 输出 vision-analysis.json，与系统 pipeline 完全兼容

用法：
  python tools/extract_video_frames.py <video_path> [选项]

选项：
  --interval SECONDS   等间隔提取时间间隔（秒），默认 5s
  --method METHOD      提取方法: interval(默认) | scene | times
  --times T1 T2 ...    指定时间点（秒），与 --method times 配合
  --threshold FLOAT    场景变化阈值 0~1，默认 0.3
  --width INT          输出帧宽度（px），默认 640
  --output DIR         输出目录，默认 <video.stem>_frames/
  --json-output FILE   vision 分析结果路径，默认 <output>/vision-analysis.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from video_mcp.vision import _key, _api_url


def _get_ffmpeg() -> str:
    """查找 ffmpeg 可执行文件。"""
    candidates = [
        os.getenv("FFMPEG_PATH"),
        shutil.which("ffmpeg"),
        shutil.which("ffmpeg.exe"),
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return str(Path(c).resolve())
    raise RuntimeError(
        "ffmpeg not found. Install ffmpeg or set FFMPEG_PATH environment variable."
    )


def _get_video_info(video: Path, ffmpeg: str) -> dict:
    """获取视频时长和分辨率。"""
    result = subprocess.run(
        [ffmpeg, "-i", str(video)],
        capture_output=True, text=True, timeout=30
    )
    info: dict = {}
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
    if m:
        h, mi, s = m.groups()
        info["duration"] = int(h) * 3600 + int(mi) * 60 + float(s)
    m = re.search(r"Stream.*Video.*(\d+)x(\d+)", result.stderr)
    if not m:
        m = re.search(r"Output.*(\d+)x(\d+)", result.stderr)
    if m:
        info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    return info


def extract_frames_at_times(
    video: Path,
    output_dir: Path,
    times: list[float],
    ffmpeg: str,
    width: int = 640,
) -> list[Path]:
    """在指定时间点各提取一帧（-ss 前置方式，最可靠）。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    for i, t in enumerate(times):
        out = output_dir / f"frame_{i+1:03d}.jpg"
        cmd = [
            ffmpeg, "-y", "-ss", f"{t:.3f}",
            "-i", str(video),
            "-vframes", "1",
            "-vf", f"scale={width}:-1",
            "-q:v", "2",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 100:
            frames.append(out)
        else:
            print(f"  ⚠️  提取 t={t:.2f}s 失败: {r.stderr[:100]}")
    return frames


def extract_frames_interval(
    video: Path,
    output_dir: Path,
    interval_seconds: float,
    ffmpeg: str,
    width: int = 640,
) -> list[Path]:
    """按固定时间间隔均匀分布提取帧。"""
    # 重新计算时间点
    info = _get_video_info(video, ffmpeg)
    dur = info.get("duration", 0)
    if dur <= 0:
        return []
    # 均匀分布：首帧、中间帧、尾帧，以及按 interval 补充
    times: list[float] = []
    t = 0.0
    while t <= dur:
        times.append(round(t, 2))
        t += interval_seconds
    # 确保首尾各有一帧
    if not times or times[0] != 0.0:
        times.insert(0, 0.0)
    if times[-1] < dur - 0.1:
        times.append(round(dur, 2))
    # 去重（浮点精度）
    times = sorted({round(t, 3) for t in times})
    return extract_frames_at_times(video, output_dir, times, ffmpeg, width)


def extract_frames_scene_change(
    video: Path,
    output_dir: Path,
    ffmpeg: str,
    threshold: float = 0.3,
    width: int = 640,
) -> list[Path]:
    """通过场景变化检测提取关键帧（适合有镜头切换的视频）。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    # 先提取所有场景变化点
    cmd = [
        ffmpeg, "-y", "-i", str(video),
        "-vf", f"select='gt(scene,{threshold:.3f})',scale={width}:-1",
        "-vf", f"select='gt(scene,{threshold:.3f})'",
        "-vsync", "vfr",
        str(output_dir / "scene_%04d.jpg"),
    ]
    # 用 filter_complex 同时做场景检测和裁剪
    cmd = [
        ffmpeg, "-y", "-i", str(video),
        "-vf", f"select='gt(scene,{threshold:.3f})',scale={width}:-1",
        "-f", "image2", "-q:v", "2",
        str(output_dir / "scene_%04d.jpg"),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0 and "Unrecognized" in r.stderr:
        # 备选方案：用 fps=1 代替场景检测
        print("  ⚠️  场景检测不可用，回退到等间隔提取")
        return extract_frames_interval(video, output_dir, 3.0, ffmpeg, width)
    frames = sorted(output_dir.glob("scene_*.jpg"))
    return frames


def _call_vision_api(
    frame_path: Path,
    api_key: str,
    model: str,
    base_url: str | None,
) -> dict:
    """调用 Vision API 分析单张图片。"""
    import base64
    import urllib.error
    import urllib.request

    mime = "image/jpeg"
    encoded = base64.b64encode(frame_path.read_bytes()).decode("ascii")
    prompt = (
        "Analyze this product video frame for a presentation. "
        "Return JSON only with: type, description, visible_text, key_points, "
        "alt_text, suggested_slide, confidence. "
        "Do not invent facts that are not visible."
    )
    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "high"},
                },
            ],
        }],
    }
    url = _api_url("openai-compatible", base_url)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return json.loads(raw["choices"][0]["message"]["content"])


def main():
    parser = argparse.ArgumentParser(
        description="从视频中提取关键帧并送入 Vision API 分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("video", help="视频文件路径")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="等间隔提取的时间间隔（秒），默认 5s")
    parser.add_argument("--method", choices=["interval", "scene", "times"],
                        default="interval")
    parser.add_argument("--times", type=float, nargs="+",
                        help="指定时间点（秒），与 --method times 配合")
    parser.add_argument("--threshold", type=float, default=0.3,
                        help="场景变化检测阈值（0~1），默认 0.3")
    parser.add_argument("--width", type=int, default=640,
                        help="输出帧宽度（px），高度自动等比，默认 640")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="输出目录，默认 <video.stem>_frames/")
    parser.add_argument("--json-output", "-j", type=Path, default=None,
                        help="Vision 分析结果路径，默认 <output>/vision-analysis.json")
    args = parser.parse_args()

    video = Path(args.video).resolve()
    if not video.exists():
        print(f"❌ 视频文件不存在: {video}")
        sys.exit(1)
    if video.suffix.lower() not in {".mp4", ".mov", ".webm", ".mkv", ".avi"}:
        print(f"❌ 不支持的视频格式: {video.suffix}")
        sys.exit(1)

    output_dir = args.output or video.parent / f"{video.stem}_frames"
    json_output = args.json_output or output_dir / "vision-analysis.json"
    ffmpeg = _get_ffmpeg()

    print(f"📹 视频: {video.name}")
    print(f"🔧 FFmpeg: {ffmpeg}")
    print(f"📁 输出目录: {output_dir}")

    # 获取视频信息
    try:
        info = _get_video_info(video, ffmpeg)
        dur = info.get("duration", 0)
        print(f"⏱  时长: {dur:.1f}s  |  📐 分辨率: {info.get('width', '?')}x{info.get('height', '?')}")
    except Exception as e:
        print(f"⚠️  无法读取视频信息: {e}")
        dur = 0

    # 提取关键帧
    print(f"\n🎬 提取关键帧 (method={args.method})...")
    frames: list[Path] = []
    if args.method == "interval":
        frames = extract_frames_interval(video, output_dir, args.interval, ffmpeg, args.width)
    elif args.method == "scene":
        frames = extract_frames_scene_change(video, output_dir, ffmpeg, args.threshold, args.width)
    elif args.method == "times":
        times = args.times or ([dur * f for f in (0.1, 0.5, 0.9)] if dur > 0 else [0])
        frames = extract_frames_at_times(video, output_dir, times, ffmpeg, args.width)

    print(f"✅ 提取到 {len(frames)} 帧")
    for f in frames:
        print(f"   {f.name}: {f.stat().st_size / 1024:.1f} KB")

    if not frames:
        print("⚠️  未提取到任何帧，请检查视频或参数")
        sys.exit(1)

    # Vision 分析
    print("\n👁  送入 Vision API 分析...")
    try:
        api_key = _key()
    except RuntimeError as e:
        print(f"❌ 缺少 API Key: {e}")
        print("   请设置 OPENAI_API_KEY 或 VIDEO_VISION_API_KEY")
        sys.exit(1)

    model = os.getenv("VIDEO_VISION_MODEL", "gpt-4.1")
    base_url = os.getenv("VIDEO_VISION_BASE_URL")

    results: list[dict] = []
    for i, frame in enumerate(frames, 1):
        print(f"   [{i}/{len(frames)}] 分析 {frame.name}...")
        try:
            analysis = _call_vision_api(frame, api_key, model, base_url)
            analysis["file"] = str(frame)
            results.append(analysis)
            print(f"      ✅ {analysis.get('type', '?')} | "
                  f"slide={analysis.get('suggested_slide', '?')} | "
                  f"confidence={analysis.get('confidence', '?')}")
        except Exception as e:
            print(f"      ❌ 分析失败: {e}")
            results.append({
                "file": str(frame),
                "type": "unknown",
                "description": "",
                "visible_text": [],
                "key_points": [],
                "alt_text": "",
                "suggested_slide": "",
                "confidence": 0.0,
                "error": str(e),
            })

    # 保存结果
    output_dir.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n💾 分析结果已保存: {json_output}")
    print(f"\n✅ 完成！成功分析 {len([r for r in results if 'error' not in r])}/{len(results)} 帧")


if __name__ == "__main__":
    main()
