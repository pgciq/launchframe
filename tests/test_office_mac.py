from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_mcp import office_mac


class MacOfficeTests(unittest.TestCase):
    def test_word_export_uses_word_save_as_pdf_script(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "brief.docx"
            pdf = root / "brief.pdf"
            source.write_bytes(b"docx")

            def fake_run(args, **kwargs):
                if args[0] == "osascript":
                    pdf.write_bytes(b"pdf")
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with (
                patch.object(office_mac.sys, "platform", "darwin"),
                patch.object(office_mac, "mac_office_app", return_value="/Applications/Microsoft Word.app"),
                patch.object(office_mac.shutil, "which", return_value="/usr/bin/tool"),
                patch.object(office_mac.subprocess, "run", side_effect=fake_run) as run,
            ):
                office_mac.export_pdf(source, pdf, "word")

            self.assertEqual(run.call_args_list[0].args[0][:3], ["open", "-a", "/Applications/Microsoft Word.app"])
            script = run.call_args_list[1].kwargs["input"]
            self.assertIn("Microsoft Word", script)
            self.assertIn("file format format PDF", script)
            self.assertTrue(pdf.exists())

    def test_excel_export_uses_excel_pdf_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "metrics.xlsx"
            pdf = root / "metrics.pdf"
            source.write_bytes(b"xlsx")

            def fake_run(args, **kwargs):
                if args[0] == "osascript":
                    pdf.write_bytes(b"pdf")
                return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with (
                patch.object(office_mac.sys, "platform", "darwin"),
                patch.object(office_mac, "mac_office_app", return_value="/Applications/Microsoft Excel.app"),
                patch.object(office_mac.shutil, "which", return_value="/usr/bin/tool"),
                patch.object(office_mac.subprocess, "run", side_effect=fake_run),
            ):
                office_mac.export_pdf(source, pdf, "excel")

            self.assertTrue(pdf.exists())


if __name__ == "__main__":
    unittest.main()
