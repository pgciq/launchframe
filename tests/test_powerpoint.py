from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_mcp import powerpoint


class MacPowerPointTests(unittest.TestCase):
    def test_available_detects_macos_powerpoint_and_osascript(self) -> None:
        with (
            patch.object(powerpoint.sys, "platform", "darwin"),
            patch.object(powerpoint, "mac_powerpoint_app", return_value="/Applications/Microsoft PowerPoint.app"),
            patch.object(powerpoint.shutil, "which", return_value="/usr/bin/osascript"),
        ):
            self.assertTrue(powerpoint.available())

    def test_export_pdf_macos_uses_osascript_and_reports_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "deck with spaces.pptx"
            pdf = root / "output.pdf"
            source.write_bytes(b"pptx")

            def fake_osascript(*args, **kwargs):
                pdf.write_bytes(b"pdf")
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with (
                patch.object(powerpoint.sys, "platform", "darwin"),
                patch.object(powerpoint, "mac_powerpoint_app", return_value="/Applications/Microsoft PowerPoint.app"),
                patch.object(powerpoint.shutil, "which", return_value="/usr/bin/osascript"),
                patch.object(powerpoint.subprocess, "run", side_effect=fake_osascript) as run,
            ):
                powerpoint.export_pdf_macos(source, pdf)

            open_command = run.call_args_list[0].args[0]
            command = run.call_args_list[1].args[0]
            script = run.call_args_list[1].kwargs["input"]
            self.assertEqual(open_command[:3], ["open", "-a", "/Applications/Microsoft PowerPoint.app"])
            self.assertEqual(command, ["osascript", "-"])
            self.assertIn("Microsoft PowerPoint", script)
            self.assertIn("deck with spaces.pptx", open_command[-1])
            self.assertTrue(pdf.exists())


if __name__ == "__main__":
    unittest.main()
