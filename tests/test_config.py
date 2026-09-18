from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_mcp.config import (
    AzureConfig,
    ContentGenerationConfig,
    ProjectConfig,
    VisionConfig,
    contained,
    project_path,
    relative_file,
    validate_project,
)


class ContainedTests(unittest.TestCase):
    def test_root_is_contained_in_itself(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(contained(root, root))

    def test_subdirectory_is_contained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(contained(root, root / "nested" / "file.txt"))

    def test_sibling_directory_is_not_contained(self) -> None:
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            self.assertFalse(contained(Path(d1), Path(d2)))


class ProjectPathTests(unittest.TestCase):
    def test_returns_the_resolved_root_when_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict("os.environ", {"VIDEO_PROJECT_ROOT": str(root)}):
                self.assertEqual(project_path(root), root.resolve())

    def test_rejects_a_directory_outside_the_allowed_root(self) -> None:
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as outside:
            with patch.dict("os.environ", {"VIDEO_PROJECT_ROOT": allowed}):
                with self.assertRaises(PermissionError):
                    project_path(outside)

    def test_rejects_a_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict("os.environ", {"VIDEO_PROJECT_ROOT": str(root)}):
                with self.assertRaises(ValueError):
                    project_path(root / "does-not-exist")


class RelativeFileTests(unittest.TestCase):
    def test_returns_the_resolved_path_when_inside_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(relative_file(root, "docs/a.md"), (root / "docs" / "a.md").resolve())

    def test_rejects_a_path_that_escapes_the_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                relative_file(root, "../outside.md")


class ValidateProjectTests(unittest.TestCase):
    def _make_config(self, root: Path, content_file: Path, **overrides) -> ProjectConfig:
        base = dict(
            root=root,
            name="p",
            version="0.1.0",
            presentation=None,
            content_files=(content_file,),
            image_files=(),
            table_files=(),
            video_files=(),
            audio_files=(),
            narration_primary=root / ".video-work" / "narration-primary.json",
            narration_secondary=root / ".video-work" / "narration-secondary.json",
            primary_language="en-US",
            secondary_language="zh-CN",
            subtitles=None,
            output_dir=root / "outputs",
            gap_seconds=0.5,
            primary_voice="v1",
            secondary_voice="v2",
            target_duration_seconds=None,
            content_generation=ContentGenerationConfig("codemie", "m", None, True),
            vision=VisionConfig(True, "codemie", "m", None, True, 5_000_000),
            azure=AzureConfig(None, None, "repo", "main", "vendor/azure-mcp"),
            draft_instructions="",
            presentation_template=None,
        )
        base.update(overrides)
        return ProjectConfig(**base)

    def test_a_well_formed_config_has_no_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content_file = root / "brief.md"
            content_file.write_text("hi", encoding="utf-8")
            self.assertEqual(validate_project(self._make_config(root, content_file)), [])

    def test_ungenerated_narration_in_video_work_is_not_an_error(self) -> None:
        # Narration is created later by the pipeline, so its absence under
        # .video-work must not block validation.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content_file = root / "brief.md"
            content_file.write_text("hi", encoding="utf-8")
            config = self._make_config(root, content_file)
            self.assertFalse(config.narration_primary.exists())
            self.assertEqual(validate_project(config), [])

    def test_primary_language_must_be_english(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content_file = root / "brief.md"
            content_file.write_text("hi", encoding="utf-8")
            errors = validate_project(self._make_config(root, content_file, primary_language="zh-CN"))
            self.assertIn("primary_language must be English", errors)

    def test_target_duration_below_thirty_seconds_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content_file = root / "brief.md"
            content_file.write_text("hi", encoding="utf-8")
            errors = validate_project(self._make_config(root, content_file, target_duration_seconds=10))
            self.assertIn("output.target_duration_seconds must be at least 30", errors)

    def test_gap_seconds_out_of_range_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content_file = root / "brief.md"
            content_file.write_text("hi", encoding="utf-8")
            errors = validate_project(self._make_config(root, content_file, gap_seconds=20))
            self.assertIn("output.gap_seconds must be between 0 and 10", errors)

    def test_image_only_project_is_valid_for_vision_and_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "product.png"
            image.write_bytes(b"image")
            errors = validate_project(self._make_config(root, image, content_files=(), image_files=(image,)))
            self.assertNotIn("Configure sources.presentation", errors)

    def test_missing_presentation_and_content_files_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content_file = root / "brief.md"
            content_file.write_text("hi", encoding="utf-8")
            errors = validate_project(self._make_config(root, content_file, content_files=()))
            self.assertIn("Configure sources.presentation, sources.presentation_sources, sources.content_files, images, or tables", errors)


    def test_multiple_presentation_sources_are_valid_for_draft_material(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.pptx"
            second = root / "b.pptx"
            first.write_bytes(b"pptx")
            second.write_bytes(b"pptx")
            config = self._make_config(root, first, content_files=(), presentation=None, presentation_sources=(first, second))
            self.assertNotIn("Configure sources.presentation", validate_project(config))


        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content_file = root / "brief.md"
            table_file = root / "specs.xlsx"
            content_file.write_text("placeholder", encoding="utf-8")
            errors = validate_project(self._make_config(root, content_file, content_files=(), table_files=(table_file,)))
            self.assertNotIn("Configure sources.presentation", errors)


        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content_file = root / "brief.md"
            content_file.write_text("hi", encoding="utf-8")
            missing = root / "missing.md"
            errors = validate_project(self._make_config(root, content_file, content_files=(missing,)))
            self.assertIn("Missing content file: missing.md", errors)


if __name__ == "__main__":
    unittest.main()
