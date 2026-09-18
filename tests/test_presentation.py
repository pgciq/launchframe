from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from video_mcp.presentation import _read_document


class SpreadsheetDocumentTests(unittest.TestCase):
    def test_reads_multiple_xlsx_sheets_and_closes_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workbook_path = root / "product-specs.xlsx"
            workbook = Workbook()
            first = workbook.active
            first.title = "Product"
            first.append(["Name", "AeroSmart"])
            first.append(["Noise", "25 dB"])
            second = workbook.create_sheet("Pricing")
            second.append(["Edition", "Price"])
            second.append(["Pro", 2999])
            workbook.save(workbook_path)
            workbook.close()

            text = _read_document(workbook_path)

            self.assertIn("Name | AeroSmart", text)
            self.assertIn("Noise | 25 dB", text)
            self.assertIn("Edition | Price", text)
            self.assertIn("Pro | 2999", text)
            workbook_path.unlink()
            self.assertFalse(workbook_path.exists())


if __name__ == "__main__":
    unittest.main()
