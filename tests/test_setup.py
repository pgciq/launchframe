from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


class SetupScriptTests(unittest.TestCase):
    def test_cross_platform_scripts_parse_and_show_help(self) -> None:
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("Bash is not available on this runner")
        root = Path(__file__).parents[1]
        for script in (root / "setup.sh", root / "run.sh"):
            self.assertTrue(script.is_file())
            syntax = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True, check=False)
            self.assertEqual(syntax.returncode, 0, syntax.stderr)
            help_result = subprocess.run([bash, str(script), "--help"], capture_output=True, text=True, check=False)
            self.assertEqual(help_result.returncode, 0, help_result.stderr)
            self.assertIn("Usage:", help_result.stdout)

    def test_python_probe_does_not_abort_on_a_stale_launcher(self) -> None:
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            self.skipTest("PowerShell is not available on this runner")

        source = Path(__file__).parents[1] / "setup.ps1"
        content = source.read_text(encoding="utf-8-sig")
        start = content.index("function Find-Command")
        end = content.index("function Find-OfficeExecutable")
        probe = (
            content[start:end]
            + '\n$ErrorActionPreference = "Stop"\n'
            + '$null = Select-Python\n'
            + 'Write-Output "python probe completed"\n'
        )
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", probe],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("python probe completed", result.stdout)


if __name__ == "__main__":
    unittest.main()
