from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from video_mcp.presentation import _read_document
from video_mcp.resources import scan


class DocumentInputTests(unittest.TestCase):
    def test_eml_text_and_metadata_are_extracted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "message.eml"
            path.write_text(
                "From: sender@example.com\nTo: user@example.com\nSubject: Product update\n"
                "Content-Type: text/plain; charset=utf-8\n\nThe release is ready.\n",
                encoding="utf-8",
            )
            text = _read_document(path)
            self.assertIn("Subject: Product update", text)
            self.assertIn("The release is ready.", text)

    def test_extended_document_formats_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("mail.eml", "page.one", "diagram.vsdx", "deck.key", "brief.pages", "data.numbers"):
                (root / name).write_bytes(b"input")
            result = scan(root)
            self.assertIn("mail.eml", result["content"])
            self.assertIn("page.one", result["content"])
            self.assertIn("diagram.vsdx", result["content"])
            self.assertIn("deck.key", result["content"])
            self.assertIn("brief.pages", result["content"])
            self.assertIn("data.numbers", result["table"])

    def test_vsdx_text_is_extracted_from_page_xml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagram.vsdx"
            with zipfile.ZipFile(path, "w") as package:
                package.writestr("visio/pages/page1.xml", "<page><shape>Architecture</shape></page>")
            self.assertIn("Architecture", _read_document(path))


if __name__ == "__main__":
    unittest.main()
