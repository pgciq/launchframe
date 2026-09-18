from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

from video_mcp.azure_mcp import account, speech_resources
from video_mcp.config import load_project, save_project_settings, validate_project
from web_gui import WEB_ROOT, PI_INTERNAL_PROVIDERS, PiBridge, choose_folder, client_disconnected, codemie_auth_valid, codemie_login, codemie_logout, cues_to_srt, normalize_codemie_credentials, normalize_vision_report, parse_vtt_cues, pi_auth_url, pi_internal_provider_status, save_pi_internal_token, vision_input_count


class WebGuiApiContractTests(unittest.TestCase):
    def test_vtt_cues_are_parsed_and_exported_as_srt(self) -> None:
        content = "WEBVTT\n\n00:00:01.000 --> 00:00:03.500\nHello\n"
        cues = parse_vtt_cues(content)
        self.assertEqual(cues[0]["start"], 1.0)
        self.assertIn("00:00:01,000 --> 00:00:03,500", cues_to_srt(cues))

    def test_service_controls_are_present(self) -> None:
        html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('<div class="bottom-actions">', html)
        self.assertIn('<button id="show-log" class="secondary" type="button">Activity log</button>', html)
        self.assertIn('<button id="service-toggle" class="danger" onclick="shutdownApplication()"', html)
        self.assertIn('id="confirm-restart"', html)
        self.assertIn('/api/restart', html)
        self.assertIn('Restarting backend service', html)
        self.assertIn('<link rel="icon" href="/favicon.ico" type="image/x-icon">', html)
        self.assertTrue((WEB_ROOT / "favicon.ico").is_file())
        self.assertIn('["azure", "Azure"', html)
        self.assertIn('["auth", "Provider"', html)
        self.assertIn('class="progress-service"', html)
        self.assertIn('id="service-state"', html)
        self.assertIn('id="backend-log-section"', html)
        self.assertIn('id="ppt-source"', html)
        self.assertIn('id="pi-internal-provider-grid"', html)
        self.assertIn('Pi-ext providers', html)
        self.assertIn('id="pi-internal-group-toggle"', html)
        self.assertIn('id="pi-extension-group-toggle"', html)
        self.assertIn('function togglePiProviderGroup(kind)', html)
        self.assertIn('id="pi-internal-toggle"', html)
        self.assertIn('function togglePiInternalProviders()', html)
        self.assertIn('pi-auth-both', html)
        self.assertIn('pi-token-controls', html)
        self.assertIn('aria-expanded="false"', html)
        self.assertIn('/api/pi/internal-providers', (Path(__file__).parents[1] / "web_gui.py").read_text(encoding="utf-8"))
        self.assertIn('function projectStorageKey(root)', html)
        self.assertIn('ai-video:last-project:${String(root || location.origin)', html)
        self.assertIn('loadWorkspaceRoot().then(async workspace => { activeProjectStorageKey = projectStorageKey(workspace.install_root || workspace.root)', html)
        self.assertIn('PVF_INSTALL_ROOT', (Path(__file__).parents[1] / "web_gui.py").read_text(encoding="utf-8"))



        self.assertIn('id="preview-primary-voice"', html)
        self.assertIn('id="preview-secondary-voice"', html)
        self.assertIn('/api/azure/voice-preview', html)
        self.assertIn('PPT approval could not be saved; audio build was not started.', html)
        self.assertNotIn('try { await post("/api/approve", { project: project(), stage: "presentation" }); } catch(_){}', html)

        self.assertIn('presentation_source_required', html)
        self.assertIn('Source PPT presentations', html)
        self.assertIn('multiple selected PPT files are combined as LLM reference material', html)



        self.assertIn('id="service-log"', html)
        self.assertIn('resize: vertical', html)
        self.assertIn('/api/service-status', html)
        self.assertIn('/api/service-log?tail=300', html)
        self.assertIn('/api/shutdown', html)
        self.assertIn("local credential was not detected", html)


    def test_pi_internal_provider_status_does_not_expose_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            auth_file = Path(directory) / "auth.json"
            auth_file.write_text(json.dumps({"github-copilot": {"type": "oauth", "access": "secret"}}), encoding="utf-8")
            with patch("web_gui.CODEMIE_AUTH_FILE", auth_file), patch.dict("web_gui.os.environ", {"OPENAI_API_KEY": "secret"}, clear=False):
                providers = {item["id"]: item for item in pi_internal_provider_status()}
        self.assertEqual(len(providers), len(PI_INTERNAL_PROVIDERS))
        self.assertTrue(providers["github-copilot"]["configured"])
        self.assertEqual(providers["github-copilot"]["source"], "Pi auth store")
        self.assertTrue(providers["openai"]["configured"])
        self.assertEqual(providers["openai"]["source"], "environment")
        self.assertNotIn("secret", json.dumps(list(providers.values())))

    def test_pi_internal_token_is_saved_in_pi_auth_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            auth_file = Path(directory) / "auth.json"
            with patch("web_gui.CODEMIE_AUTH_FILE", auth_file), patch("web_gui.PI") as pi:
                result = save_pi_internal_token("openrouter", "router-secret", True)
            data = json.loads(auth_file.read_text(encoding="utf-8"))
        self.assertEqual(result["source"], "Pi auth store")
        self.assertEqual(data["openrouter"], {"type": "api_key", "key": "router-secret"})
        pi.stop.assert_called_once_with()

    def test_vision_controls_refresh_after_model_and_config_changes(self) -> None:
        html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="vision_enabled" type="checkbox" checked onchange="markConfigDirty()"', html)
        self.assertIn("function modelSupportsVision", html)
        self.assertIn("modelActivated = true; $(\"generate-draft\").disabled = false; updateVisionOption();", html)
        self.assertIn("show(result); markConfigSaved(); await refreshStages();", html)


        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "screen.png"
            document = root / "brief.pdf"
            presentation = root / "demo.pptx"
            video = root / "demo.mp4"
            for path in (image, document, presentation, video):
                path.write_bytes(b"resource")
            config = SimpleNamespace(
                image_files=(image,),
                content_files=(document,),
                presentation=presentation,
                video_files=(video,),
            )
            self.assertEqual(vision_input_count(config), 4)

    def _fake_tk_modules(self, selected: str = "", fail: bool = False):
        tkinter = ModuleType("tkinter")
        filedialog = ModuleType("tkinter.filedialog")
        root = MagicMock()
        tkinter.Tk = MagicMock(side_effect=RuntimeError("Tk unavailable")) if fail else MagicMock(return_value=root)
        filedialog.askdirectory = MagicMock(return_value=selected)
        tkinter.filedialog = filedialog
        return tkinter, filedialog, root

    def test_folder_picker_tkinter_success_does_not_call_powershell(self) -> None:
        tkinter, filedialog, root = self._fake_tk_modules("C:\\Products\\Demo")
        with patch.dict(sys.modules, {"tkinter": tkinter, "tkinter.filedialog": filedialog}), patch("web_gui.os.name", "nt"), patch("web_gui.subprocess.run") as run:
            result = choose_folder()
        self.assertEqual(result, "C:\\Products\\Demo")
        run.assert_not_called()
        root.destroy.assert_called_once_with()

    def test_folder_picker_falls_back_to_powershell_when_tkinter_fails(self) -> None:
        tkinter, filedialog, _root = self._fake_tk_modules(fail=True)
        completed = SimpleNamespace(returncode=0, stdout="C:\\Products\\Fallback\n")
        with patch.dict(sys.modules, {"tkinter": tkinter, "tkinter.filedialog": filedialog}), patch("web_gui.os.name", "nt"), patch("web_gui.subprocess.run", return_value=completed) as run:
            result = choose_folder()
        self.assertEqual(result, "C:\\Products\\Fallback")
        self.assertIn("FolderBrowserDialog", " ".join(run.call_args.args[0]))

    def test_folder_picker_cancel_returns_empty_path(self) -> None:
        tkinter, filedialog, root = self._fake_tk_modules("")
        with patch.dict(sys.modules, {"tkinter": tkinter, "tkinter.filedialog": filedialog}), patch("web_gui.os.name", "nt"), patch("web_gui.subprocess.run") as run:
            result = choose_folder()
        self.assertEqual(result, "")
        run.assert_not_called()
        root.destroy.assert_called_once_with()

    def test_folder_picker_returns_selected_path(self) -> None:
        tkinter, filedialog, _root = self._fake_tk_modules("D:\\Product Resources")
        with patch.dict(sys.modules, {"tkinter": tkinter, "tkinter.filedialog": filedialog}), patch("web_gui.os.name", "nt"):
            self.assertEqual(choose_folder(), "D:\\Product Resources")


        self.assertEqual(
            pi_auth_url({"method": "notify", "message": {"type": "auth_url", "url": "https://codemie.example/login"}}),
            "https://codemie.example/login",
        )
        self.assertEqual(pi_auth_url({"method": "notify", "message": "status"}), "")

    def test_vision_report_paths_are_relative_to_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "assets" / "product.png"
            image.parent.mkdir()
            image.write_bytes(b"image")
            report = normalize_vision_report(root, [{"file": str(image), "source_file": str(image)}])
            self.assertEqual(report[0]["file"], "assets/product.png")
            self.assertEqual(report[0]["source_file"], "assets/product.png")

    def test_vision_report_recovers_paths_from_a_moved_project_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "mock-product"
            image = root / "assets" / "product.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"image")
            old_path = r"D:\\old-repository\\examples\\mock-product\\assets\\product.png"
            report = normalize_vision_report(root, [{"file": old_path}])
            self.assertEqual(report[0]["file"], "assets/product.png")


        class FakeStdin:
            def write(self, _value: str) -> None:
                return None

            def flush(self) -> None:
                return None

        class FakeProcess:
            stdin = FakeStdin()

            def poll(self):
                return None

        bridge = PiBridge()
        bridge.process = FakeProcess()
        bridge.events.put({"type": "agent_end", "messages": []})
        bridge.events.put({"id": "request-id", "type": "response", "success": True})
        with patch("web_gui.uuid.uuid4", return_value=SimpleNamespace(hex="request-id")):
            result = bridge.request({"type": "prompt", "message": "/login codemie"}, wait_for_agent=True)
        self.assertTrue(result["accepted"])

    def test_codemie_normalization_prefers_valid_shared_cli_credential(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            auth_file = Path(directory) / "auth.json"
            auth_file.write_text(json.dumps({
                "codemie": {"type": "oauth", "access": "stale", "refresh": "stale-refresh", "expires": 1},
                "codemie-cli": {"type": "oauth", "access": "valid", "refresh": "valid-refresh", "expires": (time.time() + 3600) * 1000},
                "other": {"type": "api_key", "key": "unchanged"},
            }), encoding="utf-8")
            self.assertTrue(normalize_codemie_credentials(auth_file))
            data = json.loads(auth_file.read_text(encoding="utf-8"))
            self.assertEqual(data["codemie"]["access"], "valid")
            self.assertEqual(data["codemie-cli"]["refresh"], "valid-refresh")
            self.assertEqual(data["other"]["key"], "unchanged")

    def test_codemie_auth_accepts_shared_cli_credential_and_epoch_seconds(self) -> None:
        future_seconds = 4_000_000_000
        self.assertTrue(codemie_auth_valid({"codemie-cli": {"access": "token", "expires": future_seconds}}))
        self.assertTrue(codemie_auth_valid({"codemie": {"access": "expired", "refresh": "refresh-token", "expires": 1}}))
        self.assertFalse(codemie_auth_valid({"codemie": {"access": "token", "expires": 1}}))

    def test_codemie_login_waits_for_agent_completion(self) -> None:
        with patch("web_gui.PI") as pi:
            pi.request.return_value = {"accepted": True}
            result = codemie_login("C:/product")
            pi.start.assert_called_once_with("C:/product")
            pi.request.assert_called_once_with(
                {"type": "prompt", "message": "/login codemie"},
                wait_for_agent=True,
                collect_notifications=True,
            )
            self.assertEqual(result, {"accepted": True})

    def test_codemie_logout_waits_for_agent_completion(self) -> None:
        with patch("web_gui.PI") as pi:
            pi.request.return_value = {"accepted": True}
            result = codemie_logout("C:/product")
            pi.start.assert_called_once_with("C:/product")
            pi.request.assert_called_once_with(
                {"type": "prompt", "message": "/logout codemie"},
                wait_for_agent=True,
            )
            self.assertEqual(result, {"accepted": True})

    def test_client_disconnect_is_not_treated_as_an_application_error(self) -> None:
        self.assertTrue(client_disconnected(ConnectionAbortedError(10053, "connection aborted")))
        self.assertTrue(client_disconnected(ConnectionResetError(10054, "connection reset")))
        self.assertFalse(client_disconnected(ValueError("application error")))

    def test_account_uses_the_azure_cli_session_when_available(self) -> None:
        cli_output = '[{"id": "sub-1", "name": "Production", "state": "Enabled"}]'
        completed = SimpleNamespace(returncode=0, stdout=cli_output, stderr="")
        with patch("video_mcp.azure_mcp.az_command", return_value="az"), patch("video_mcp.azure_mcp.subprocess.run", return_value=completed) as run:
            result = account(SimpleNamespace(root=Path("."), azure=SimpleNamespace(checkout_dir="vendor/azure-mcp")))
        run.assert_called_once_with(
            ["az", "account", "list", "--output", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(result, [{"subscription_id": "sub-1", "display_name": "Production", "state": "Enabled"}])

    def test_speech_resources_uses_azure_cli_and_ignores_child_resources(self) -> None:
        cli_output = (
            '[{"id": "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/speech", '
            '"name": "speech", "resourceGroup": "rg", "location": "eastus", '
            '"type": "Microsoft.CognitiveServices/accounts"}, '
            '{"id": "/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.CognitiveServices/accounts/speech/projects/demo", '
            '"name": "speech/demo", "resourceGroup": "rg", "location": "eastus", '
            '"type": "Microsoft.CognitiveServices/accounts/projects"}]'
        )
        completed = SimpleNamespace(returncode=0, stdout=cli_output, stderr="")
        config = SimpleNamespace(root=Path("."), azure=SimpleNamespace(checkout_dir="vendor/azure-mcp", subscription_id=None))
        with patch("video_mcp.azure_mcp.az_command", return_value="az"), patch("video_mcp.azure_mcp.subprocess.run", return_value=completed):
            result = speech_resources(config, "sub-1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "speech")
        self.assertEqual(result[0].resource_group, "rg")

    def test_subscription_response_is_normalized_for_gui(self) -> None:
        with patch("video_mcp.azure_mcp.az_command", side_effect=RuntimeError("Azure CLI unavailable")), patch("video_mcp.azure_mcp._call", return_value=[
            {"scope_id": "sub-1", "display_name": "Production", "state": "Enabled"},
        ]):
            result = account(SimpleNamespace(root=Path("."), azure=SimpleNamespace(checkout_dir="vendor/azure-mcp")))
        self.assertEqual(result, [{"subscription_id": "sub-1", "display_name": "Production", "state": "Enabled"}])

    def test_missing_subscription_id_is_ignored(self) -> None:
        with patch("video_mcp.azure_mcp.az_command", side_effect=RuntimeError("Azure CLI unavailable")), patch("video_mcp.azure_mcp._call", return_value=[{"display_name": "invalid"}, "invalid"]):
            result = account(SimpleNamespace(root=Path("."), azure=SimpleNamespace(checkout_dir="vendor/azure-mcp")))
        self.assertEqual(result, [])

    def test_resource_folder_does_not_require_video_project_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"VIDEO_PROJECT_ROOT": directory}):
            root = Path(directory)
            (root / "product-brief.md").write_text("A product", encoding="utf-8")
            config = load_project(root)
            self.assertEqual(config.root, root.resolve())
            self.assertTrue(config.content_files)
            self.assertEqual(validate_project(config), [])
            saved = save_project_settings(root, {"name": "product", "sources": {"auto_scan": True}})
            self.assertNotEqual(saved, root / "video-project.json")
            self.assertTrue(saved.exists())
            self.assertFalse((root / "video-project.json").exists())



if __name__ == "__main__":
    unittest.main()
