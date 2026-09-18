from __future__ import annotations

import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WindowsInstallationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.install_bat = (ROOT / "install.bat").read_text(encoding="utf-8")
        cls.unblock_bat = (ROOT / "unblock-scripts.bat").read_text(encoding="utf-8")
        cls.run_ps1 = (ROOT / "run.ps1").read_text(encoding="utf-8")
        cls.setup_ps1 = (ROOT / "setup.ps1").read_text(encoding="utf-8")
        cls.setup_ps1 = (ROOT / "setup.ps1").read_text(encoding="utf-8")
        cls.shortcut_ps1 = (ROOT / "scripts" / "create-shortcut.ps1").read_text(encoding="utf-8")
        cls.debug_bat = (ROOT / "debug.bat").read_text(encoding="utf-8")
        cls.uninstall_bat = (ROOT / "uninstall.bat").read_text(encoding="utf-8")
        cls.uninstall_ps1 = (ROOT / "scripts" / "uninstall.ps1").read_text(encoding="utf-8")

    def test_install_sequence_is_fail_fast_and_ordered(self) -> None:
        unblock = self.install_bat.index('call "%ROOT%unblock-scripts.bat"')
        setup = self.install_bat.index('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%setup.ps1" -InstallMissing')
        shortcut = self.install_bat.index('powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\\create-shortcut.ps1"')
        self.assertIn('set "PROJECT_ROOT=%ROOT:~0,-1%"', self.install_bat)
        self.assertIn('-ProjectRoot "%PROJECT_ROOT%"', self.install_bat)
        start_prompt = self.install_bat.index('START_NOW=')
        self.assertLess(unblock, setup)
        self.assertLess(setup, shortcut)
        self.assertLess(shortcut, start_prompt)
        self.assertIn('START_NOW=Start LaunchFrame now? [Y/n]:', self.install_bat)
        self.assertIn('if /I "%START_NOW%"=="" set "START_NOW=Y"', self.install_bat)
        self.assertGreaterEqual(self.install_bat.count("if errorlevel 1"), 3)

    def test_install_uses_process_scoped_execution_policy_bypass(self) -> None:
        self.assertIn("-ExecutionPolicy Bypass", self.install_bat)
        self.assertIn("-ExecutionPolicy Bypass", self.unblock_bat)
        self.assertIn("-ExecutionPolicy Bypass", self.shortcut_ps1)

    def test_setup_installs_ffmpeg_from_winget(self) -> None:
        setup = self.setup_ps1
        self.assertIn('Id = "Gyan.FFmpeg.Shared"', setup)
        self.assertIn('Name = "FFmpeg"', setup)
        self.assertIn('winget install --id $package.Id', setup)
        self.assertNotIn('tools\\install-ffmpeg.ps1', setup)


        self.assertIn("LaunchFrame.lnk", self.shortcut_ps1)
        self.assertIn("run.ps1", self.shortcut_ps1)
        self.assertIn("$ProjectRoot = $ProjectRoot.Trim().Trim('\"')", self.shortcut_ps1)
        self.assertIn("launchframe.ico", self.shortcut_ps1)
        self.assertIn("-WindowStyle Hidden", self.shortcut_ps1)
        self.assertTrue((ROOT / "assets" / "launchframe.ico").is_file())

    def test_setup_checks_minimum_node_and_pi_versions(self) -> None:
        self.assertIn('$minimumNodeVersion = [version]"22.19.0"', self.setup_ps1)
        self.assertIn('$minimumPiVersion = [version]"0.85.1"', self.setup_ps1)
        self.assertIn("Installing/updating Pi CLI", self.setup_ps1)
        self.assertIn("@earendil-works/pi-coding-agent@latest", self.setup_ps1)

    def test_run_script_supports_runtime_tracking_duplicate_detection_and_debug(self) -> None:
        self.assertNotIn("[switch]$Debug", self.run_ps1)
        for marker in (
            "web-gui-runtime.json",
            "Get-CimInstance Win32_Process",
            "taskkill.exe /PID",
            "Confirm-ReplaceExisting",
            "WindowStyle = \"Hidden\"",
            "RedirectStandardOutput",
            "web-gui-error.log",
            "--debug",
        ):
            self.assertIn(marker, self.run_ps1)

    def test_run_refreshes_registry_environment_for_ffmpeg_and_install_root(self) -> None:
        for marker in (
            'PVF_INSTALL_ROOT',
            '[Environment]::GetEnvironmentVariable("Path", $scope)',
            '[Environment]::GetEnvironmentVariable("Path", $scope)',
            'Find-FfmpegExecutable',
            '$env:FFMPEG_PATH',
            'ffmpeg_path = $env:FFMPEG_PATH',
        ):
            self.assertIn(marker, self.run_ps1)

    def test_run_persists_install_root_in_runtime_manifest(self) -> None:
        self.assertIn('install_root = $root', self.run_ps1)
        self.assertIn('web-gui-runtime.json', self.run_ps1)


        self.assertIn("run.ps1\" -Debug", self.debug_bat)

    def test_uninstaller_is_fail_safe_and_preserves_user_data(self) -> None:
        self.assertIn("scripts\\uninstall.ps1", self.uninstall_bat)
        self.assertIn("-ExecutionPolicy Bypass", self.uninstall_bat)
        for marker in (".install-manifest.json", "LaunchFrame.lnk", "taskkill.exe /PID", "Product resource folders", "$Purge", "$RemoveInstallationDirectory", "Type DELETE"):
            self.assertIn(marker, self.uninstall_ps1)
        self.assertNotIn("Remove-Item -LiteralPath $root -Recurse -Force", self.uninstall_ps1)

    def test_uninstaller_does_not_remove_shared_tools_by_default(self) -> None:
        self.assertIn("winget_installed", self.uninstall_ps1)
        self.assertIn("npm_installed", self.uninstall_ps1)
        self.assertIn("Shared Winget tools", self.uninstall_ps1)
        self.assertIn("Shared npm packages", self.uninstall_ps1)


    @unittest.skipUnless(os.name == "nt", "PowerShell syntax validation requires Windows")
    def test_windows_powershell_scripts_parse(self) -> None:
        scripts = [ROOT / "setup.ps1", ROOT / "run.ps1", ROOT / "scripts" / "create-shortcut.ps1", ROOT / "scripts" / "uninstall.ps1"]
        for script in scripts:
            command = (
                "$null = [scriptblock]::Create((Get-Content -Raw -LiteralPath "
                f"'{script}'));"
            )
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", command],
                check=True,
                capture_output=True,
                text=True,
            )


if __name__ == "__main__":
    unittest.main()
