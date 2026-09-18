from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from video_mcp.pipeline import build_project


class PresentationOnlyBuildTests(unittest.TestCase):
    def test_presentation_build_does_not_resolve_speech(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root / ".video-work"
            output_dir = root / "outputs"
            presentation = work / "generated-presentation.pptx"
            published_presentation = output_dir / "presentation.pptx"
            work.mkdir()
            (work / "content-draft.json").write_text(json.dumps({
                "outline": [{"slide": 1, "title": "Overview", "key_points": ["Product"]}],
                "primary_narration": [],
                "secondary_narration": [],
            }), encoding="utf-8")
            config = SimpleNamespace(
                root=root,
                name="product",
                version="0.1.0",
                presentation=None,
                image_files=(),
                output_dir=output_dir,
                vision=SimpleNamespace(enabled=False),
                narration_primary=work / "narration-primary.json",
                narration_secondary=work / "narration-secondary.json",
                presentation_template=None,
            )

            def write_presentation(*args, **kwargs) -> None:
                presentation.parent.mkdir(parents=True, exist_ok=True)
                presentation.write_bytes(b"pptx")

            def write_pdf(*args, **kwargs) -> Path:
                output_dir.mkdir(parents=True, exist_ok=True)
                pdf = output_dir / "presentation.pdf"
                pdf.write_bytes(b"pdf")
                return pdf

            with (
                patch("video_mcp.pipeline.validate_project", return_value=[]),
                patch("video_mcp.pipeline.create_presentation_from_outline", side_effect=write_presentation),
                patch("video_mcp.pipeline.render_presentation_pdf", side_effect=write_pdf),
                patch("video_mcp.pipeline._approved", return_value=True),
                patch("video_mcp.pipeline.resolve_speech", side_effect=AssertionError("Speech must not be resolved for PPT-only builds")),
            ):
                result = build_project(config, stop_after="presentation")

            self.assertEqual(result["presentation"], str(published_presentation))
            self.assertEqual(published_presentation.read_bytes(), b"pptx")
            self.assertEqual(result["pdf"], str(output_dir / "presentation.pdf"))


if __name__ == "__main__":
    unittest.main()
