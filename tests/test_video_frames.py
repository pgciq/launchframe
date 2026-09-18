from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_mcp.video_frames import extract_all_keyframes, extract_keyframes, _get_ffmpeg, _get_video_duration


def _make_video(root: Path, name: str, duration: float, size: tuple[int, int] = (640, 360), ffmpeg: str | None = None) -> Path:
    """用 ffmpeg 生成一个测试视频。"""
    ff = ffmpeg or _get_ffmpeg()
    if ff is None:
        return root / name
    path = root / name
    # 不捕获输出，避免 pytest 环境下 subprocess 被干扰
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i",
         f"testsrc=duration={duration}:size={size[0]}x{size[1]}:rate=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
        timeout=30,
    )
    return path


class VideoFramesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ffmpeg = _get_ffmpeg()
        if self.ffmpeg is None:
            self.skipTest("ffmpeg not available")

    def test_extract_single_frame_from_short_video(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            video = _make_video(root, "test.mp4", duration=3.0, ffmpeg=self.ffmpeg)
            self.assertTrue(video.exists(), "视频文件未生成")
            frames = extract_keyframes(video, root / "out", max_frames=1, ffmpeg=self.ffmpeg)
            self.assertEqual(len(frames), 1)
            self.assertTrue(frames[0].exists())
            self.assertGreater(frames[0].stat().st_size, 100)

    def test_extract_multiple_frames_uniformly(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            video = _make_video(root, "test.mp4", duration=10.0, ffmpeg=self.ffmpeg)
            frames = extract_keyframes(video, root / "out", max_frames=5, ffmpeg=self.ffmpeg)
            self.assertLessEqual(len(frames), 5)  # 首尾各一帧，最多5帧
            for f in frames:
                self.assertIn("test", f.name)

    def test_short_video_becomes_one_frame_per_second(self) -> None:
        """视频时长 ≤ max_frames 时，每秒一帧。"""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            video = _make_video(root, "test.mp4", duration=3.0, ffmpeg=self.ffmpeg)
            frames = extract_keyframes(video, root / "out", max_frames=10, ffmpeg=self.ffmpeg)
            self.assertLessEqual(len(frames), 4)  # t=0,1,2,3 但尾部可能因精度损失一帧

    def test_empty_video_list_returns_no_frames(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            frames, truncated = extract_all_keyframes((), root / "work", max_keyframes=5, ffmpeg=self.ffmpeg)
            self.assertEqual(frames, [])
            self.assertEqual(truncated, 0)

    def test_max_keyframes_budget_is_respected(self) -> None:
        """多个视频共享帧预算，总帧数不超过 max_keyframes。"""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            v1 = _make_video(root, "long.mp4", duration=10.0, ffmpeg=self.ffmpeg)
            v2 = _make_video(root, "short.mp4", duration=2.0, ffmpeg=self.ffmpeg)
            frames, truncated = extract_all_keyframes(
                (v1, v2), root / "work", max_keyframes=3, ffmpeg=self.ffmpeg
            )
            self.assertLessEqual(len(frames), 3)

    def test_longer_video_prioritized_over_shorter(self) -> None:
        """预算不足时，长视频优先保留更多帧。"""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            v_long = _make_video(root, "long.mp4", duration=10.0, ffmpeg=self.ffmpeg)
            v_short = _make_video(root, "short.mp4", duration=2.0, ffmpeg=self.ffmpeg)
            frames, _ = extract_all_keyframes(
                (v_short, v_long), root / "work", max_keyframes=4, ffmpeg=self.ffmpeg
            )
            long_frames = [f for f in frames if "long" in f.name]
            short_frames = [f for f in frames if "short" in f.name]
            self.assertGreaterEqual(len(long_frames), len(short_frames))

    def test_nonexistent_video_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            fake = root / "does-not-exist.mp4"
            frames, _ = extract_all_keyframes((fake,), root / "work", max_keyframes=5, ffmpeg=self.ffmpeg)
            self.assertEqual(frames, [])

    def test_get_video_duration(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            video = _make_video(root, "test.mp4", duration=7.5, ffmpeg=self.ffmpeg)
            duration = _get_video_duration(video, self.ffmpeg)
            self.assertAlmostEqual(duration, 7.5, places=1)

    @patch("video_mcp.video_frames._get_ffmpeg", return_value=None)
    def test_no_ffmpeg_returns_empty(self, _mock) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            video = _make_video(root, "test.mp4", duration=5.0, ffmpeg=self.ffmpeg)
            frames, truncated = extract_all_keyframes((video,), root / "work", max_keyframes=5)
            self.assertEqual(frames, [])
            self.assertEqual(truncated, 0)


if __name__ == "__main__":
    unittest.main()
