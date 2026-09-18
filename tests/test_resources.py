from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from video_mcp.resources import is_presentation_template, presentation_candidates, scan


class ScanTests(unittest.TestCase):
    def test_categorizes_files_by_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "deck.pptx").write_text("x", encoding="utf-8")
            (root / "brief.md").write_text("x", encoding="utf-8")
            (root / "logo.png").write_text("x", encoding="utf-8")
            (root / "prices.csv").write_text("x", encoding="utf-8")
            (root / "clip.mp4").write_text("x", encoding="utf-8")
            (root / "voice.mp3").write_text("x", encoding="utf-8")
            result = scan(root)
            self.assertEqual(result["presentation"], ["deck.pptx"])
            self.assertEqual(result["content"], ["brief.md"])
            self.assertEqual(result["image"], ["logo.png"])
            self.assertEqual(result["table"], ["prices.csv"])
            self.assertEqual(result["video"], ["clip.mp4"])
            self.assertEqual(result["audio"], ["voice.mp3"])

    def test_ignores_managed_directories_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".video-work").mkdir()
            (root / ".video-work" / "narration-primary.json").write_text("[]", encoding="utf-8")
            (root / "outputs").mkdir()
            (root / "outputs" / "final.mp4").write_text("x", encoding="utf-8")
            (root / "video-project.json").write_text("{}", encoding="utf-8")
            result = scan(root)
            self.assertEqual(result["narration"], [])
            self.assertEqual(result["video"], [])
            self.assertEqual(sum(len(v) for v in result.values()), 0)

    def test_detects_narration_files_by_language_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "narration.en-US.json").write_text("[]", encoding="utf-8")
            (root / "narration.zh-CN.json").write_text("[]", encoding="utf-8")
            (root / "narration.txt").write_text("not narration", encoding="utf-8")
            result = scan(root)
            self.assertEqual(
                sorted(result["narration"]),
                ["narration.en-US.json", "narration.zh-CN.json"],
            )
            self.assertEqual(result["content"], ["narration.txt"])

    def test_detects_subtitles_by_folder_or_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "subtitles").mkdir()
            (root / "subtitles" / "captions.txt").write_text("x", encoding="utf-8")
            (root / "standalone.vtt").write_text("x", encoding="utf-8")
            result = scan(root)
            self.assertEqual(
                sorted(result["subtitle"]),
                ["standalone.vtt", "subtitles/captions.txt"],
            )

    def test_excludes_generated_presentation_outputs_from_source_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.pptx").write_bytes(b"source")
            (root / "templates").mkdir()
            (root / "templates" / "brand.pptx").write_bytes(b"template")
            (root / "outputs").mkdir()
            (root / "outputs" / "presentation.pptx").write_bytes(b"generated")

            self.assertEqual(
                presentation_candidates(root),
                ["source.pptx", "templates/brand.pptx"],
            )

    def test_classifies_template_presentation_paths(self) -> None:
        self.assertTrue(is_presentation_template("templates/brand.pptx"))
        self.assertTrue(is_presentation_template("brand.template.pptx"))
        self.assertFalse(is_presentation_template("product-overview.pptx"))


        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            (root / "nested" / "logo.png").write_text("x", encoding="utf-8")
            result = scan(root)
            self.assertEqual(result["image"], ["nested/logo.png"])
            self.assertNotIn("\\", result["image"][0])


if __name__ == "__main__":
    unittest.main()
