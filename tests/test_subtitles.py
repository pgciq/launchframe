from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from video_mcp.subtitles import (
    _as_cue,
    generate_subtitles,
    proportional_timings,
    split_display_chunks,
    split_sentences,
    timestamp,
    write_srt,
    write_vtt,
)


class SplitSentencesTests(unittest.TestCase):
    def test_splits_english_on_terminal_punctuation(self) -> None:
        self.assertEqual(
            split_sentences("Hello world. This is a test!", "en-US"),
            ["Hello world.", "This is a test!"],
        )

    def test_splits_chinese_on_full_width_punctuation(self) -> None:
        self.assertEqual(
            split_sentences("你好世界。这是一个测试！", "zh-CN"),
            ["你好世界。", "这是一个测试！"],
        )

    def test_short_sentence_is_single_one_line_cue(self) -> None:
        chunks = split_display_chunks("Hello world.", "en-US")
        self.assertEqual(chunks, ["Hello world."])
        self.assertNotIn("\n", chunks[0])

    def test_medium_sentence_becomes_single_two_line_cue(self) -> None:
        # 83-char sentence: fits within 2×56=112, must stay as ONE cue
        sentence = "LaunchFrame is a review-gated workspace for creating multilingual videos."
        chunks = split_display_chunks(sentence, "en-US")
        self.assertEqual(len(chunks), 1)
        self.assertIn("\n", chunks[0])
        for line in chunks[0].split("\n"):
            self.assertLessEqual(len(line), 56)

    def test_splits_long_latin_sentence_into_two_line_cues(self) -> None:
        # 152-char string: exceeds 2×56=112, must produce multiple cues
        chunks = split_display_chunks("This is a very long narration sentence " * 4, "en-US")
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            for line in chunk.split("\n"):
                self.assertLessEqual(len(line), 56)

    def test_splits_long_cjk_sentence_into_two_line_cues(self) -> None:
        # 60-char CJK string: exceeds 2×24=48, must produce multiple cues
        chunks = split_display_chunks("这是一个很长的中文旁白句子" * 5, "zh-CN")
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            for line in chunk.split("\n"):
                self.assertLessEqual(len(line), 24)

    def test_as_cue_wraps_long_line_with_newline(self) -> None:
        # 83-char string must be split into two lines each ≤ 56 chars
        sentence = "LaunchFrame is a review-gated workspace for creating videos."
        result = _as_cue(sentence, 56, False)
        self.assertIn("\n", result)
        for line in result.split("\n"):
            self.assertLessEqual(len(line), 56)

    def test_as_cue_leaves_short_text_unchanged(self) -> None:
        self.assertEqual(_as_cue("Hello.", 56, False), "Hello.")



class TimestampTests(unittest.TestCase):
    def test_formats_srt_style_with_comma(self) -> None:
        self.assertEqual(timestamp(1.5), "00:00:01,500")

    def test_formats_vtt_style_with_dot(self) -> None:
        self.assertEqual(timestamp(1.5, vtt=True), "00:00:01.500")

    def test_handles_hours_and_minutes(self) -> None:
        self.assertEqual(timestamp(3661.001), "01:01:01,001")

    def test_zero_seconds(self) -> None:
        self.assertEqual(timestamp(0.0), "00:00:00,000")


class ProportionalTimingsTests(unittest.TestCase):
    def test_empty_text_returns_no_cues(self) -> None:
        self.assertEqual(proportional_timings("", "en-US", 10.0), [])

    def test_cues_are_contiguous_and_cover_the_full_duration(self) -> None:
        cues = proportional_timings("Hello world. This is a test!", "en-US", 10.0)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0]["start"], 0.0)
        self.assertAlmostEqual(cues[-1]["end"], 10.0)
        self.assertAlmostEqual(cues[0]["end"], cues[1]["start"])

    def test_longer_sentences_get_a_larger_share_of_the_duration(self) -> None:
        cues = proportional_timings("Hi. This sentence is much longer than the first one!", "en-US", 10.0)
        first_span = cues[0]["end"] - cues[0]["start"]
        second_span = cues[1]["end"] - cues[1]["start"]
        self.assertGreater(second_span, first_span)


class WriteSrtVttTests(unittest.TestCase):
    def test_write_srt_produces_expected_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.srt"
            write_srt(path, [(0.0, 1.5, "Hello"), (1.5, 3.0, "World")])
            content = path.read_text(encoding="utf-8")
            self.assertIn("1\n00:00:00,000 --> 00:00:01,500\nHello", content)
            self.assertIn("2\n00:00:01,500 --> 00:00:03,000\nWorld", content)

    def test_write_vtt_includes_header_and_dot_separator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.vtt"
            write_vtt(path, [(0.0, 1.5, "Hello")])
            content = path.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("WEBVTT\n"))
            self.assertIn("00:00:00.000 --> 00:00:01.500", content)


class GenerateSubtitlesTests(unittest.TestCase):
    def _write_fixtures(self, root: Path) -> dict[str, Path]:
        primary_narration = root / "narration.en.json"
        secondary_narration = root / "narration.zh.json"
        primary_manifest = root / "primary-manifest.json"
        secondary_manifest = root / "secondary-manifest.json"
        primary_narration.write_text(
            json.dumps([{"slide": 1, "text": "Hello world. This is great!"}]),
            encoding="utf-8",
        )
        secondary_narration.write_text(
            json.dumps([{"slide": 1, "text": "你好世界。这很棒！"}]),
            encoding="utf-8",
        )
        primary_manifest.write_text(
            json.dumps({"slides": [{"slide": 1, "duration_seconds": 4.0}]}),
            encoding="utf-8",
        )
        secondary_manifest.write_text(
            json.dumps({"slides": [{"slide": 1, "duration_seconds": 5.0}]}),
            encoding="utf-8",
        )
        return {
            "primary_narration": primary_narration,
            "secondary_narration": secondary_narration,
            "primary_manifest": primary_manifest,
            "secondary_manifest": secondary_manifest,
        }

    def test_generates_all_six_subtitle_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = self._write_fixtures(root)
            output_dir = root / "out"
            paths = generate_subtitles(
                fixtures["primary_narration"],
                fixtures["secondary_narration"],
                fixtures["primary_manifest"],
                fixtures["secondary_manifest"],
                output_dir,
                "en-US",
                "zh-CN",
            )
            self.assertEqual(
                set(paths),
                {"primary_srt", "secondary_srt", "bilingual_srt", "primary_vtt", "secondary_vtt", "bilingual_vtt"},
            )
            for path in paths.values():
                self.assertTrue(Path(path).exists())

    def test_bilingual_cue_contains_both_languages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = self._write_fixtures(root)
            output_dir = root / "out"
            paths = generate_subtitles(
                fixtures["primary_narration"],
                fixtures["secondary_narration"],
                fixtures["primary_manifest"],
                fixtures["secondary_manifest"],
                output_dir,
                "en-US",
                "zh-CN",
            )
            bilingual = Path(paths["bilingual_srt"]).read_text(encoding="utf-8")
            self.assertIn("Hello world.", bilingual)
            self.assertIn("你好世界。", bilingual)

    def test_slide_duration_uses_the_longer_of_the_two_languages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixtures = self._write_fixtures(root)
            output_dir = root / "out"
            generate_subtitles(
                fixtures["primary_narration"],
                fixtures["secondary_narration"],
                fixtures["primary_manifest"],
                fixtures["secondary_manifest"],
                output_dir,
                "en-US",
                "zh-CN",
            )
            # Secondary manifest duration (5.0s) is longer than primary (4.0s).
            secondary_srt = (output_dir / "presentation-secondary.srt").read_text(encoding="utf-8")
            self.assertIn("00:00:05,000", secondary_srt)


if __name__ == "__main__":
    unittest.main()
