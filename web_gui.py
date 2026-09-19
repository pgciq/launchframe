from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from video_mcp.azure_mcp import (
    account,
    login,
    login_status,
    logout,
    resolve_speech,
    speech_resources,
)
from video_mcp.cancellation import CancellationRequested
from video_mcp.config import (
    load_project,
    project_settings,
    save_project_settings,
)
from video_mcp.pipeline import build_project, inspect_project
from video_mcp.presentation import _read_document
from video_mcp import mac_documents, office_mac, powerpoint
from video_mcp.render import audio_duration, resolve_ffmpeg
from video_mcp.resources import is_presentation_template, presentation_candidates, scan
from video_mcp.speech import synthesize_voice_preview
from video_mcp.state import read_state

_MAX_VIDEO_FRAMES = 12       # cap per video file
_MIN_FRAME_INTERVAL = 5.0   # never faster than 1 frame per 5 s

ROOT = Path(__file__).parent
WEB_ROOT = ROOT / "web"
TOKEN_SERVICE = "launchframe"
_CLIENT_DISCONNECT_CODES = {995, 10053, 10054, 104}  # Win32 abort/reset, WSAECONNABORTED/RESET, POSIX reset


def client_disconnected(error: BaseException) -> bool:
    """Return whether a browser closed the socket before the response finished."""
    return (
        isinstance(error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError))
        or getattr(error, "winerror", None) in _CLIENT_DISCONNECT_CODES
        or getattr(error, "errno", None) in _CLIENT_DISCONNECT_CODES
    )


def read_service_log(tail: int = 300) -> str:
    """Return a bounded, source-labelled tail of local service logs."""
    tail = max(1, min(int(tail), 1000))
    sections: list[str] = []
    for label, path in (("web", SERVICE_LOG_PATH), ("web-error", SERVICE_ERROR_LOG_PATH), ("pi", PI_LOG_PATH)):
        try:
            if path.exists():
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
                sections.extend(f"[{label}] {line}" for line in lines[-tail:])
        except OSError as error:
            sections.append(f"[{label}] Could not read {path.name}: {error}")
    return "\n".join(sections[-tail:]) or "No backend log output is available yet."


def token_store_get(provider: str) -> str:
    try:
        import keyring
        return keyring.get_password(TOKEN_SERVICE, provider) or ""
    except Exception as error:  # noqa: BLE001
        _ = error
        return ""


def token_store_set(provider: str, token: str) -> None:
    import keyring
    keyring.set_password(TOKEN_SERVICE, provider, token)


def token_store_delete(provider: str) -> None:
    try:
        import keyring
        keyring.delete_password(TOKEN_SERVICE, provider)
    except Exception as error:  # noqa: BLE001
        _ = error


def provider_token_name(provider: str) -> str:
    return {"dial": "DIAL_API_KEY", "elitea": "ELITEA_API_TOKEN"}[provider]


def hydrate_provider_token(provider: str) -> bool:
    if provider not in {"dial", "elitea"}:
        return False
    token = os.environ.get(provider_token_name(provider), "") or token_store_get(provider)
    if token:
        PI.set_provider_token(provider, token)
        return True
    return False


CODEMIE_AUTH_FILE = Path.home() / ".pi" / "agent" / "auth.json"

# Providers owned by Pi rather than by the product workflow.  Keep these out
# of the main provider picker for now: the workflow still needs its own
# provider contract, but the Web GUI can inspect and later promote any of
# these providers without hard-coding auth logic into the page.
PI_INTERNAL_PROVIDERS: tuple[dict[str, str], ...] = (
    {"id": "openai-codex", "name": "OpenAI Codex / ChatGPT", "auth": "account", "env": "", "login": "/login openai-codex"},
    {"id": "anthropic", "name": "Anthropic / Claude", "auth": "account or token", "env": "ANTHROPIC_API_KEY", "login": "/login anthropic"},
    {"id": "github-copilot", "name": "GitHub Copilot", "auth": "account", "env": "", "login": "/login github-copilot"},
    {"id": "xai", "name": "xAI / Grok", "auth": "account or token", "env": "XAI_API_KEY", "login": "/login xai"},
    {"id": "openrouter", "name": "OpenRouter", "auth": "account or token", "env": "OPENROUTER_API_KEY", "login": "/login openrouter"},
    {"id": "radius", "name": "Radius", "auth": "account or token", "env": "RADIUS_API_KEY", "login": "/login radius"},
    {"id": "openai", "name": "OpenAI API", "auth": "token", "env": "OPENAI_API_KEY", "login": "/login openai"},
    {"id": "kimi-coding", "name": "Kimi for Coding", "auth": "token", "env": "KIMI_API_KEY", "login": "/login kimi-coding"},
    {"id": "google", "name": "Google Gemini", "auth": "token or ambient account", "env": "GEMINI_API_KEY", "login": "/login google"},
    {"id": "deepseek", "name": "DeepSeek", "auth": "token", "env": "DEEPSEEK_API_KEY", "login": "/login deepseek"},
    {"id": "ant-ling", "name": "Ant Ling", "auth": "token", "env": "ANT_LING_API_KEY", "login": "/login ant-ling"},
    {"id": "baseten", "name": "Baseten", "auth": "token", "env": "BASETEN_API_KEY", "login": "/login baseten"},
    {"id": "zai", "name": "ZAI Coding Plan (Global)", "auth": "token", "env": "ZAI_API_KEY", "login": "/login zai"},
    {"id": "zai-coding-cn", "name": "ZAI Coding Plan (China)", "auth": "token", "env": "ZAI_CODING_CN_API_KEY", "login": "/login zai-coding-cn"},
    {"id": "mistral", "name": "Mistral", "auth": "token", "env": "MISTRAL_API_KEY", "login": "/login mistral"},
    {"id": "groq", "name": "Groq", "auth": "token", "env": "GROQ_API_KEY", "login": "/login groq"},
    {"id": "cerebras", "name": "Cerebras", "auth": "token", "env": "CEREBRAS_API_KEY", "login": "/login cerebras"},
    {"id": "nvidia", "name": "NVIDIA NIM", "auth": "token", "env": "NVIDIA_API_KEY", "login": "/login nvidia"},
    {"id": "minimax", "name": "MiniMax", "auth": "token", "env": "MINIMAX_API_KEY", "login": "/login minimax"},
    {"id": "minimax-cn", "name": "MiniMax (China)", "auth": "token", "env": "MINIMAX_CN_API_KEY", "login": "/login minimax-cn"},
    {"id": "qwen-token-plan", "name": "Qwen Token Plan", "auth": "token", "env": "QWEN_TOKEN_PLAN_API_KEY", "login": "/login qwen-token-plan"},
    {"id": "qwen-token-plan-individual", "name": "Qwen Token Plan (Individual)", "auth": "token", "env": "QWEN_TOKEN_PLAN_API_KEY", "login": "/login qwen-token-plan-individual"},
    {"id": "qwen-token-plan-cn", "name": "Qwen Token Plan (China)", "auth": "token", "env": "QWEN_TOKEN_PLAN_CN_API_KEY", "login": "/login qwen-token-plan-cn"},
    {"id": "xiaomi", "name": "Xiaomi MiMo", "auth": "token", "env": "XIAOMI_API_KEY", "login": "/login xiaomi"},
    {"id": "xiaomi-token-plan-cn", "name": "Xiaomi MiMo Token Plan (China)", "auth": "token", "env": "XIAOMI_TOKEN_PLAN_CN_API_KEY", "login": "/login xiaomi-token-plan-cn"},
    {"id": "xiaomi-token-plan-ams", "name": "Xiaomi MiMo Token Plan (Amsterdam)", "auth": "token", "env": "XIAOMI_TOKEN_PLAN_AMS_API_KEY", "login": "/login xiaomi-token-plan-ams"},
    {"id": "xiaomi-token-plan-sgp", "name": "Xiaomi MiMo Token Plan (Singapore)", "auth": "token", "env": "XIAOMI_TOKEN_PLAN_SGP_API_KEY", "login": "/login xiaomi-token-plan-sgp"},
    {"id": "fireworks", "name": "Fireworks", "auth": "token", "env": "FIREWORKS_API_KEY", "login": "/login fireworks"},
    {"id": "together", "name": "Together AI", "auth": "token", "env": "TOGETHER_API_KEY", "login": "/login together"},
    {"id": "huggingface", "name": "Hugging Face", "auth": "token", "env": "HF_TOKEN", "login": "/login huggingface"},
    {"id": "opencode", "name": "OpenCode Zen", "auth": "token", "env": "OPENCODE_API_KEY", "login": "/login opencode"},
    {"id": "opencode-go", "name": "OpenCode Go", "auth": "token", "env": "OPENCODE_API_KEY", "login": "/login opencode-go"},
    {"id": "cloudflare-ai-gateway", "name": "Cloudflare AI Gateway", "auth": "token", "env": "CLOUDFLARE_API_KEY", "login": "/login cloudflare-ai-gateway"},
    {"id": "cloudflare-workers-ai", "name": "Cloudflare Workers AI", "auth": "token", "env": "CLOUDFLARE_API_KEY", "login": "/login cloudflare-workers-ai"},
    {"id": "amazon-bedrock", "name": "Amazon Bedrock", "auth": "account or token", "env": "AWS_BEARER_TOKEN_BEDROCK", "login": "/login amazon-bedrock"},
    {"id": "azure-openai-responses", "name": "Azure OpenAI", "auth": "token", "env": "AZURE_OPENAI_API_KEY", "login": "/login azure-openai-responses"},
)

# Providers registered by the optional pi-cn-free-model-providers extension.
# They are intentionally kept separate from Pi's built-in provider inventory.
PI_EXTENSION_PROVIDERS: tuple[dict[str, str], ...] = (
    {"id": "opencode-zen", "name": "OpenCode Zen (extension)", "auth": "public or token", "env": "OPENCODE_API_KEY", "login": ""},
    {"id": "sensenova", "name": "SenseNova (extension)", "auth": "public or token", "env": "SENSENOVA_API_KEY", "login": ""},
    {"id": "siliconflow", "name": "SiliconFlow (extension)", "auth": "public or token", "env": "SILICONFLOW_API_KEY", "login": ""},
    {"id": "modelscope", "name": "ModelScope (extension)", "auth": "public or token", "env": "MODELSCOPE_API_KEY", "login": ""},
    {"id": "amd", "name": "AMD Radeon Cloud (extension)", "auth": "public or token", "env": "AMD_API_KEY", "login": ""},
    {"id": "cloudflare", "name": "Cloudflare Workers AI (extension)", "auth": "public or token", "env": "CLOUDFLARE_API_KEY", "login": ""},
    {"id": "agnes", "name": "Agnes AI (international, extension)", "auth": "public or token", "env": "AGNES_API_KEY", "login": ""},
    {"id": "agnes-cn", "name": "Agnes AI (China, extension)", "auth": "public or token", "env": "AGNES_CN_API_KEY", "login": ""},
)

PI_INTERNAL_PROVIDER_IDS = {provider["id"] for provider in PI_INTERNAL_PROVIDERS}
PI_EXTENSION_PROVIDER_IDS = {provider["id"] for provider in PI_EXTENSION_PROVIDERS}
PI_PROVIDER_IDS = PI_INTERNAL_PROVIDER_IDS | PI_EXTENSION_PROVIDER_IDS


def pi_extension_installed() -> bool:
    package_root = Path.home() / ".pi" / "agent" / "npm" / "node_modules" / "pi-cn-free-model-providers"
    if package_root.exists():
        return True
    settings_path = Path.home() / ".pi" / "agent" / "settings.json"
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        return any("pi-cn-free-model-providers" in str(item) for item in settings.get("packages", []))
    except (OSError, ValueError, TypeError):
        return False


def pi_internal_provider_status() -> list[dict[str, str | bool]]:
    """Return Pi's built-in provider inventory without exposing credentials."""
    try:
        auth_data = json.loads(CODEMIE_AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        auth_data = {}
    result: list[dict[str, str | bool]] = []
    for provider in PI_INTERNAL_PROVIDERS:
        credential = auth_data.get(provider["id"], {}) if isinstance(auth_data, dict) else {}
        stored_in_pi = isinstance(credential, dict) and bool(
            credential.get("key") or credential.get("access") or credential.get("refresh")
        )
        pi_bridge = globals().get("PI")
        session_environment = getattr(pi_bridge, "provider_env", {}) if pi_bridge else {}
        stored_in_env = bool(provider["env"] and (os.environ.get(provider["env"], "") or session_environment.get(provider["env"], "")))
        sources = []
        if stored_in_pi:
            sources.append("Pi auth store")
        if stored_in_env:
            sources.append("session/environment" if session_environment.get(provider["env"], "") else "environment")
        result.append({
            **provider,
            "configured": bool(sources),
            "source": ", ".join(sources) if sources else "none",
        })
    return result


def pi_extension_provider_status() -> list[dict[str, str | bool]]:
    installed = pi_extension_installed()
    try:
        auth_data = json.loads(CODEMIE_AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        auth_data = {}
    pi_bridge = globals().get("PI")
    session_environment = getattr(pi_bridge, "provider_env", {}) if pi_bridge else {}
    result: list[dict[str, str | bool]] = []
    for provider in PI_EXTENSION_PROVIDERS:
        credential = auth_data.get(provider["id"], {}) if isinstance(auth_data, dict) else {}
        stored_in_pi = isinstance(credential, dict) and bool(credential.get("key") or credential.get("access") or credential.get("refresh"))
        stored_in_env = bool(provider["env"] and (os.environ.get(provider["env"], "") or session_environment.get(provider["env"], "")))
        sources = []
        if installed and "public" in provider["auth"]:
            sources.append("extension public")
        if stored_in_pi:
            sources.append("Pi auth store")
        if stored_in_env:
            sources.append("session/environment" if session_environment.get(provider["env"], "") else "environment")
        result.append({
            **provider,
            "extension": True,
            "installed": installed,
            "configured": bool(sources),
            "source": ", ".join(sources) if sources else ("extension not installed" if not installed else "none"),
        })
    return result


def get_pi_internal_provider(provider_id: str) -> dict[str, str] | None:
    return next((provider for provider in PI_INTERNAL_PROVIDERS if provider["id"] == provider_id), None)


def get_pi_provider(provider_id: str) -> dict[str, str] | None:
    return get_pi_internal_provider(provider_id) or next((provider for provider in PI_EXTENSION_PROVIDERS if provider["id"] == provider_id), None)


def save_pi_internal_token(provider_id: str, token: str, remember: bool) -> dict[str, object]:
    """Save a Pi-native API token using Pi's auth.json format."""
    provider = get_pi_provider(provider_id)
    if not provider or "token" not in provider["auth"]:
        raise ValueError("This Pi provider does not support token authentication")
    if provider_id in PI_EXTENSION_PROVIDER_IDS and not pi_extension_installed():
        raise ValueError("The Pi extension for this provider is not installed")
    token = token.strip()
    if not token:
        raise ValueError("Token is required")

    try:
        auth_data = json.loads(CODEMIE_AUTH_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        auth_data = {}
    if not isinstance(auth_data, dict):
        auth_data = {}
    if remember:
        auth_data[provider_id] = {"type": "api_key", "key": token}
    else:
        # A session-only token must not be shadowed by an older persisted key.
        auth_data.pop(provider_id, None)
    CODEMIE_AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CODEMIE_AUTH_FILE.with_suffix(CODEMIE_AUTH_FILE.suffix + ".tmp")
    temporary.write_text(json.dumps(auth_data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(CODEMIE_AUTH_FILE)

    environment = provider["env"]
    if environment:
        if remember:
            PI.provider_env.pop(environment, None)
        else:
            PI.provider_env[environment] = token
    PI.stop()
    return {
        "provider": provider_id,
        "token_persisted": remember,
        "source": "Pi auth store" if remember else "session environment",
    }


def codemie_auth_valid(data: dict) -> bool:
    """Return whether either shared CodeMie SSO credential is available."""
    now_ms = time.time() * 1000
    for provider in ("codemie", "codemie-cli"):
        credential = data.get(provider, {}) if isinstance(data, dict) else {}
        try:
            expires = float(credential.get("expires", 0))
            if 0 < expires < 10_000_000_000:  # tolerate epoch seconds from older auth files
                expires *= 1000
            if credential.get("access") and (expires > now_ms or credential.get("refresh")):
                return True
        except (TypeError, ValueError):
            continue
    return False


def normalize_codemie_credentials(auth_file: Path | None = None) -> bool:
    """Put the best shared CodeMie credential in the plugin's first slot.

    pi-codemie checks ``codemie`` before ``codemie-cli``. If the former has an
    expired access token while the latter still has a valid shared session, the
    plugin can unnecessarily start a new SSO flow. Keep both slots synchronized
    so either provider starts from the same usable credential.
    """
    path = auth_file or CODEMIE_AUTH_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        candidates = [(provider, data.get(provider, {})) for provider in ("codemie", "codemie-cli")]
        candidates = [(provider, credential) for provider, credential in candidates if isinstance(credential, dict) and credential.get("access")]
        if not candidates:
            return False
        now_ms = time.time() * 1000
        def rank(item: tuple[str, dict]) -> tuple[int, float, int]:
            provider, credential = item
            try:
                expires = float(credential.get("expires", 0))
                if 0 < expires < 10_000_000_000:
                    expires *= 1000
            except (TypeError, ValueError):
                expires = 0
            return (1 if expires > now_ms else 0, expires, 1 if provider == "codemie-cli" else 0)
        selected_provider, selected = max(candidates, key=rank)
        current = data.get("codemie", {})
        if selected_provider == "codemie" and current == selected:
            return False
        if selected_provider == "codemie-cli" and rank(("codemie", current)) >= rank((selected_provider, selected)):
            return False
        shared = {key: selected[key] for key in ("type", "refresh", "access", "expires") if key in selected}
        shared["type"] = "oauth"
        data["codemie"] = dict(shared)
        data["codemie-cli"] = dict(shared)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)
        return True
    except (OSError, ValueError, TypeError):
        return False


def relative_project_path(root: Path, value: str | Path) -> str:
    """Convert an in-project absolute path to a safe project-relative path."""
    raw = str(value)
    path = PureWindowsPath(raw) if "\\" in raw or (len(raw) > 1 and raw[1] == ":") else Path(raw)
    candidate = path if isinstance(path, PureWindowsPath) and path.is_absolute() else (root / Path(raw.replace("\\", "/"))).resolve()
    try:
        return candidate.relative_to(root.resolve()).as_posix()
    except (ValueError, TypeError):
        # Reports created before a project directory was moved may contain the
        # old absolute prefix. Recover a matching path under the current root.
        parts = list(path.parts)
        root_name = root.name.lower()
        for index, part in enumerate(parts):
            if part.lower() == root_name:
                remapped = root.joinpath(*parts[index + 1:])
                if remapped.is_file():
                    return remapped.resolve().relative_to(root.resolve()).as_posix()
        return raw.replace("\\", "/")


def normalize_vision_report(root: Path, report: list[dict]) -> list[dict]:
    """Normalize Vision image/source paths for storage and current-project URLs."""
    normalized: list[dict] = []
    for item in report:
        entry = dict(item)
        for key in ("file", "source_file"):
            if entry.get(key):
                entry[key] = relative_project_path(root, str(entry[key]))
        normalized.append(entry)
    return normalized


def pi_auth_url(event: dict) -> str:
    """Extract an OAuth browser URL from a Pi RPC notify event."""
    message = event.get("message")
    if isinstance(message, dict) and message.get("type") == "auth_url":
        return str(message.get("url", "")).strip()
    if event.get("type") == "auth_url":
        return str(event.get("url", "")).strip()
    return ""
EXECUTOR = ThreadPoolExecutor(max_workers=1)
JOBS: dict[str, dict] = {}
CANCEL_EVENTS: dict[str, threading.Event] = {}
WS_CLIENTS: set = set()
HTTP_SERVER: ThreadingHTTPServer | None = None
SERVICE_INFO: dict[str, object] = {}
RUNTIME_PATH = ROOT / ".video-work" / "web-gui-runtime.json"
SERVICE_LOG_PATH = ROOT / ".video-work" / "web-gui.log"
SERVICE_ERROR_LOG_PATH = ROOT / ".video-work" / "web-gui-error.log"
PI_LOG_PATH = ROOT / ".video-work" / "pi.log"


def restart_service_process() -> int:
    """Start a replacement Web GUI process before the current one exits."""
    host = str(SERVICE_INFO.get("host", "127.0.0.1"))
    port = int(SERVICE_INFO.get("port", 8875))
    websocket_port = int(SERVICE_INFO.get("websocket_port", port + 1))
    service_python = sys.executable
    if os.name == "nt":
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            service_python = str(pythonw)
    command = [service_python, "-m", "web_gui", "--host", host, "--port", str(port), "--websocket-port", str(websocket_port)]
    if SERVICE_INFO.get("debug"):
        command.append("--debug")
    # Keep the child PID stable while it waits for the old HTTP socket to close.
    bootstrap = "import os,sys,time; time.sleep(1.0); os.execv(sys.argv[1], sys.argv[1:])"
    SERVICE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log = SERVICE_LOG_PATH.open("a", encoding="utf-8")
    error_log = SERVICE_ERROR_LOG_PATH.open("a", encoding="utf-8")
    flags = 0
    startupinfo = None
    if os.name == "nt":
        flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
    try:
        child = subprocess.Popen(
            [service_python, "-c", bootstrap, *command],
            cwd=str(ROOT),
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=error_log,
            close_fds=True,
            creationflags=flags,
            startupinfo=startupinfo,
            start_new_session=os.name != "nt",
        )
    finally:
        log.close()
        error_log.close()
    RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_PATH.write_text(json.dumps({
        "pid": child.pid,
        "host": host,
        "port": port,
        "websocket_port": websocket_port,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "debug": bool(SERVICE_INFO.get("debug")),
        "log_path": str(SERVICE_LOG_PATH),
        "error_log_path": str(SERVICE_ERROR_LOG_PATH),
        "root": str(ROOT),
        "install_root": str(ROOT),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return child.pid


def _raise_agent_error(agent_end: dict) -> None:
    """Raise RuntimeError if the agent ended with an error stopReason.

    Pi returns ``stopReason: "error"`` when the active model/API combination
    fails (for example ``openAICompletionsApi is not defined`` for models that
    use the ``openai-completions`` API with a provider that only supports
    ``openai-responses``). Surface that message directly so the user knows
    which model to pick instead of seeing the generic 'Pi finished without
    creating' fallback.
    """
    messages = agent_end.get("messages", [])
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        if msg.get("stopReason") == "error":
            raw = str(msg.get("errorMessage") or "Unknown Pi agent error")
            model = msg.get("model", "")
            api = msg.get("api", "")
            hint = ""
            if "not defined" in raw or "undefined" in raw.lower():
                hint = (
                    f" The model '{model}' uses the '{api}' API which is not "
                    "supported by this provider. Switch to a model that uses "
                    "the 'openai-responses' API (e.g. GPT-5.6 Luna or GPT-5.6 "
                    "Terra) and try again."
                )
            sep = "" if raw.endswith(".") or raw.endswith("!") or raw.endswith("?") else "."
            raise RuntimeError(f"Pi agent error: {raw}{sep}{hint}")


class PiBridge:
    """Small JSON-RPC bridge for the local Pi process used by the Web GUI."""

    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.project: str = ""
        self.provider_env: dict[str, str] = {}
        self.stderr_file = None
        self.events: queue.Queue[dict] = queue.Queue()
        self.lock = threading.RLock()

    def _reader(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            try:
                self.events.put(json.loads(line))
            except json.JSONDecodeError:
                continue

    def start(self, project: str = "") -> None:
        if not str(project).strip():
            raise ValueError("Select a product resource directory before starting Pi.")
        root = load_project(project).root
        with self.lock:
            if self.process and self.process.poll() is None and self.project == str(root):
                return
            self.stop()
            normalize_codemie_credentials()
            command = os.environ.get("PI_COMMAND") or shutil.which("pi.cmd") or shutil.which("pi")
            if not command:
                raise RuntimeError("Pi executable was not found. Install pi or set PI_COMMAND.")
            pi_args = ["--mode", "rpc", "--no-session", "--approve", "--extension", str(ROOT / "pi" / "extensions" / "video-workflow.ts")]
            command_args = [command, *pi_args]
            if os.name == "nt" and str(command).lower().endswith((".cmd", ".bat")):
                command_path = Path(command)
                node_path = command_path.with_name("node.exe")
                cli_path = command_path.parent / "node_modules" / "@earendil-works" / "pi-coding-agent" / "dist" / "bundle" / "cli.js"
                if node_path.exists() and cli_path.exists():
                    # Avoid launching a .cmd wrapper: direct node execution is
                    # reliably hidden and prevents a conhost window flashing.
                    command_args = [str(node_path), str(cli_path), *pi_args]
            PI_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.stderr_file = PI_LOG_PATH.open("a", encoding="utf-8")
            startupinfo = None
            creationflags = 0
            if os.name == "nt":
                creationflags = (
                    getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                    | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                )
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0  # SW_HIDE
            try:
                self.process = subprocess.Popen(
                    command_args,
                    cwd=str(ROOT),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=self.stderr_file,
                    env={**os.environ, **self.provider_env},
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    creationflags=creationflags,
                    startupinfo=startupinfo,
                )
            except Exception:
                self.stderr_file.close()
                self.stderr_file = None
                raise
            self.project = str(root)
            threading.Thread(target=self._reader, args=(self.process,), daemon=True).start()

    def set_provider_token(self, provider: str, token: str) -> None:
        names = {"dial": "DIAL_API_KEY", "elitea": "ELITEA_API_TOKEN"}
        if provider not in names:
            raise ValueError("Token authentication is only used by DIAL and ELITEA")
        name = names[provider]
        if self.provider_env.get(name) == token:
            return
        self.provider_env[name] = token
        self.stop()

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            if os.name == "nt":
                # pi.cmd can leave its node child alive when only the wrapper
                # is terminated. Kill the complete process tree on restart.
                subprocess.run(
                    ["taskkill.exe", "/PID", str(self.process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            else:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
        self.process = None
        self.project = ""
        self.events = queue.Queue()
        if self.stderr_file:
            self.stderr_file.close()
            self.stderr_file = None

    def request(self, command: dict, wait_for_agent: bool = False, timeout: float = 900, collect_notifications: bool = False) -> dict:
        with self.lock:
            if not self.process or self.process.poll() is not None or not self.process.stdin:
                raise RuntimeError("Pi is not running.")
            request_id = uuid.uuid4().hex
            command = {**command, "id": request_id}
            self.process.stdin.write(json.dumps(command, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
            accepted = False
            agent_finished = False
            notifications: list[dict] = []
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    event = self.events.get(timeout=max(0.1, deadline - time.monotonic()))
                except queue.Empty as error:
                    raise TimeoutError("Pi did not respond in time.") from error
                if event.get("type") == "extension_ui_request":
                    if event.get("method") == "notify":
                        if collect_notifications:
                            notifications.append(event)
                        # Pi's OAuth provider emits the browser URL through a
                        # fire-and-forget notify event. A TUI opens it itself;
                        # the Web GUI must do that explicitly. Notify events do
                        # not expect an extension_ui_response.
                        auth_url = pi_auth_url(event)
                        if auth_url:
                            try:
                                webbrowser.open_new_tab(auth_url)
                            except Exception as error:  # noqa: BLE001 - browser launch is best effort.
                                _ = error
                        continue
                    # The Web GUI has no TUI dialog. Login URL notifications
                    # are handled above; unexpected dialogs are cancelled
                    # rather than blocking Pi.
                    if self.process.stdin:
                        self.process.stdin.write(json.dumps({"type": "extension_ui_response", "id": event.get("id"), "cancelled": True}) + "\n")
                        self.process.stdin.flush()
                    continue
                if not self.process or self.process.poll() is not None:
                    raise CancellationRequested("Pi operation cancelled")
                if event.get("type") == "agent_end":
                    _raise_agent_error(event)
                    agent_finished = True
                    if wait_for_agent and accepted:
                        return {"accepted": True, "agent_end": event, "notifications": notifications}
                    continue
                if event.get("id") == request_id and event.get("type") == "response":
                    if not event.get("success"):
                        raise RuntimeError(event.get("error", f"Pi command {command.get('type')} failed."))
                    accepted = True
                    if not wait_for_agent:
                        return {"response": event, "notifications": notifications} if collect_notifications else event
                    if agent_finished:
                        return {"accepted": True, "notifications": notifications}

            raise TimeoutError("Pi agent did not finish in time.")

    def status(self) -> dict:
        auth_file = CODEMIE_AUTH_FILE
        authenticated = False
        try:
            data = json.loads(auth_file.read_text(encoding="utf-8"))
            authenticated = codemie_auth_valid(data)
        except (OSError, ValueError, TypeError):
            pass
        return {
            "running": bool(self.process and self.process.poll() is None),
            "project": self.project,
            "codemie_authenticated": authenticated,
        }


PI = PiBridge()


CODEMIE_AUTH_LOCK = threading.Lock()
MODEL_TEST_LOCK = threading.Lock()


def codemie_login(project: str) -> dict:
    if not CODEMIE_AUTH_LOCK.acquire(blocking=False):
        raise RuntimeError("CodeMie authentication is already in progress. Complete the current browser login first.")
    try:
        PI.start(project)
        return PI.request(
            {"type": "prompt", "message": "/login codemie"},
            wait_for_agent=True,
            collect_notifications=True,
        )
    finally:
        CODEMIE_AUTH_LOCK.release()


def codemie_logout(project: str) -> dict:
    if not CODEMIE_AUTH_LOCK.acquire(blocking=False):
        raise RuntimeError("CodeMie authentication is already in progress. Complete it before logging out.")
    try:
        PI.start(project)
        return PI.request(
            {"type": "prompt", "message": "/logout codemie"},
            wait_for_agent=True,
        )
    finally:
        CODEMIE_AUTH_LOCK.release()


def pi_internal_login(provider_id: str, project: str) -> dict:
    provider = get_pi_internal_provider(provider_id)
    if not provider or "account" not in provider["auth"]:
        raise ValueError("This Pi provider does not support account login")
    if not CODEMIE_AUTH_LOCK.acquire(blocking=False):
        raise RuntimeError("Another Pi provider login is already in progress.")
    try:
        PI.start(project)
        return PI.request(
            {"type": "prompt", "message": f"/login {provider_id}"},
            wait_for_agent=True,
            collect_notifications=True,
        )
    finally:
        CODEMIE_AUTH_LOCK.release()


def pi_model_test(provider: str, model_id: str, project: str) -> dict[str, object]:
    """Run a bounded, read-only one-token smoke test through Pi."""
    provider = provider.strip().lower()
    model_id = model_id.strip()
    if not provider or not model_id:
        raise ValueError("provider and model_id are required")
    if provider in {"dial", "elitea"}:
        if not hydrate_provider_token(provider):
            raise ValueError(f"{provider.upper()} token is not configured.")
    elif provider in PI_PROVIDER_IDS:
        inventory = pi_internal_provider_status() + pi_extension_provider_status()
        item = next(item for item in inventory if item["id"] == provider)
        if not item["configured"]:
            raise ValueError(f"{provider} is not authenticated or its extension is not installed.")
    elif provider in {"codemie", "codemie-cli"}:
        if not PI.status()["codemie_authenticated"]:
            raise ValueError("CodeMie is not authenticated.")
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    started = time.monotonic()
    with MODEL_TEST_LOCK:
        try:
            PI.start(project)
            PI.request({"type": "set_model", "provider": provider, "modelId": model_id}, timeout=20)
            result = PI.request(
                {
                    "type": "prompt",
                    "message": "Reply with exactly OK. This is a short connectivity test. Do not use tools, inspect files, or modify anything.",
                },
                wait_for_agent=True,
                timeout=25,
            )
        except Exception:
            # A timed-out provider can leave the agent busy. Restarting Pi makes
            # the next model test independent and avoids contaminating a result.
            PI.stop()
            raise
    text = ""
    for message in reversed((result.get("agent_end") or {}).get("messages", [])):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content", "")
        text = content if isinstance(content, str) else "".join(
            item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"
        )
        if text.strip():
            break
    return {
        "provider": provider,
        "model_id": model_id,
        "ok": bool(text.strip()),
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "response_preview": text.strip()[:120],
    }


def pi_json_result(result: dict) -> object | None:
    event = result.get("agent_end", {}) if isinstance(result, dict) else {}
    for message in reversed(event.get("messages", [])):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content", [])
        text = content if isinstance(content, str) else "".join(item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text")
        if "```" in text:
            parts = text.split("```")
            text = next((part for part in parts if "{" in part or "[" in part), text)
            text = text.removeprefix("json").strip()
        start = min((index for index in (text.find("{"), text.find("[")) if index >= 0), default=-1)
        end = max(text.rfind("}"), text.rfind("]"))
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    return None


def _safe_com_close(obj, method: str, *args) -> None:
    if obj is None:
        return
    try:
        getattr(obj, method)(*args)
    except Exception as error:  # noqa: BLE001
        _ = error


def _convert_to_pdf(source: Path, dest_dir: Path) -> Path:
    """Convert Office documents using native Office automation when available."""
    pdf = dest_dir / f"{source.stem}.pdf"
    converted = False
    suffix = source.suffix.lower()
    if sys.platform == "darwin" and not converted:
        try:
            if suffix in {".pptx", ".ppt"} and powerpoint.available():
                powerpoint.export_pdf_macos(source, pdf)
                converted = pdf.exists()
            elif suffix in {".docx", ".doc"} and office_mac.available("word"):
                office_mac.export_pdf(source, pdf, "word")
                converted = pdf.exists()
            elif suffix in {".xlsx", ".xls"} and office_mac.available("excel"):
                office_mac.export_pdf(source, pdf, "excel")
                converted = pdf.exists()
            elif suffix in {".pages", ".numbers", ".key"}:
                kind = {".pages": "pages", ".numbers": "numbers", ".key": "keynote"}[suffix]
                if mac_documents.available(kind):
                    mac_documents.export_pdf(source, pdf, kind)
                    converted = pdf.exists()
        except Exception:  # noqa: BLE001
            converted = False
    if os.name == "nt" and not converted:
        try:
            import win32com.client
            if suffix in {".pptx", ".ppt"}:
                app = win32com.client.DispatchEx("PowerPoint.Application")
                app.Visible = False  # type: ignore[attr-defined]
                pres = app.Presentations.Open(str(source), ReadOnly=True, Untitled=False, WithWindow=False)
                pres.ExportAsFixedFormat(str(pdf), 2)  # ppFixedFormatTypePDF = 2
                pres.Close()
                app.Quit()
            elif suffix in {".xlsx", ".xls"}:
                app = win32com.client.DispatchEx("Excel.Application")
                app.Visible = False
                app.DisplayAlerts = False
                workbook = app.Workbooks.Open(str(source), ReadOnly=True, UpdateLinks=False)
                workbook.ExportAsFixedFormat(0, str(pdf))  # xlTypePDF = 0
                workbook.Close(False)
                app.Quit()
            elif suffix in {".vsdx", ".vsd"}:
                app = win32com.client.DispatchEx("Visio.Application")
                app.Visible = False
                document = app.Documents.Open(str(source))
                document.ExportAsFixedFormat(1, str(pdf), 1)  # visFixedFormatPDF, screen intent
                document.Close()
                app.Quit()
            else:
                app = win32com.client.DispatchEx("Word.Application")
                app.Visible = False
                app.DisplayAlerts = 0
                doc = app.Documents.Open(str(source), ReadOnly=True, AddToRecentFiles=False, Visible=False)
                doc.ExportAsFixedFormat(str(pdf), 17)
                doc.Close(False)
                app.Quit()
            converted = pdf.exists()
        except Exception:  # noqa: BLE001
            converted = False
    if not converted:
        soffice = shutil.which("soffice") or shutil.which("soffice.exe")
        if not soffice:
            raise RuntimeError(f"{source.suffix.upper()} Vision analysis requires Microsoft Office or LibreOffice.")
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(dest_dir), str(source)],
            check=True, capture_output=True,
        )
        converted = pdf.exists()
    if not converted:
        raise RuntimeError(f"Could not convert {source.name} to PDF for Vision analysis.")
    return pdf


def _extract_video_frames(video: Path, work: Path) -> list[dict[str, object]]:
    """Extract evenly-spaced frames from a video for Vision analysis."""
    try:
        ffmpeg = resolve_ffmpeg(video.parent)
    except RuntimeError:
        return []
    try:
        duration = audio_duration(video, ffmpeg)
    except RuntimeError:
        return []
    if duration < _MIN_FRAME_INTERVAL:
        return []
    interval = max(duration / _MAX_VIDEO_FRAMES, _MIN_FRAME_INTERVAL)
    frame_count = min(_MAX_VIDEO_FRAMES, max(1, int(duration / interval)))
    output_pattern = str(work / f"{video.stem}-vframe-%04d.png")
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", str(video),
             "-vf", f"fps=1/{interval:.1f},scale=1280:-2",
             "-frames:v", str(frame_count),
             "-q:v", "2", output_pattern],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError:
        return []
    frames = sorted(work.glob(f"{video.stem}-vframe-*.png"))
    results: list[dict[str, object]] = []
    for i, frame_path in enumerate(frames):
        secs = int(i * interval)
        m, s = divmod(secs, 60)
        results.append({"path": frame_path, "source_file": str(video), "page": None, "frame_time": f"{m}:{s:02d}"})
    return results


def vision_input_count(config) -> int:
    """Count configured resources that can produce Vision inputs for the GUI."""
    return (
        len(config.image_files)
        + sum(1 for path in config.content_files if path.suffix.lower() in {".pdf", ".docx", ".doc", ".vsdx", ".vsd", ".pages", ".key"})
        + sum(1 for path in getattr(config, "table_files", ()) if path.suffix.lower() in {".xlsx", ".xls", ".numbers"})
        + int(bool(config.presentation and config.presentation.suffix.lower() in {".pptx", ".ppt"}))
        + sum(1 for path in getattr(config, "presentation_sources", ()) if path.suffix.lower() in {".pptx", ".ppt"})
        + len(config.video_files)
    )


def vision_input_pages(config) -> list[dict[str, object]]:
    """Prepare images, PDF pages, DOCX/PPTX slides, and video frames for the Vision model."""
    import fitz

    work = config.root / ".video-work" / "vision-pages"
    work.mkdir(parents=True, exist_ok=True)
    inputs: list[dict[str, object]] = [
        {"path": image, "source_file": str(image), "page": None, "frame_time": None}
        for image in config.image_files
    ]

    # PDF / Office pages + PPTX slides
    renderable_content = [p for p in config.content_files if p.suffix.lower() in {".pdf", ".docx", ".doc", ".vsdx", ".vsd", ".pages", ".key"}]
    renderable_content.extend(path for path in getattr(config, "table_files", ()) if path.suffix.lower() in {".xlsx", ".xls", ".numbers"} and path.exists())
    pptx_sources = [config.presentation] if config.presentation and config.presentation.suffix.lower() in {".pptx", ".ppt"} and config.presentation.exists() else []
    pptx_sources.extend(path for path in getattr(config, "presentation_sources", ()) if path.suffix.lower() in {".pptx", ".ppt"} and path.exists())
    for source in renderable_content + pptx_sources:
        temp_context = tempfile.TemporaryDirectory(prefix="launchframe-render-") if source.suffix.lower() != ".pdf" else None
        temp_dir = Path(temp_context.name) if temp_context else source.parent
        try:
            pdf = source if source.suffix.lower() == ".pdf" else _convert_to_pdf(source, temp_dir)
            document = fitz.open(str(pdf))
            try:
                for page_number, page in enumerate(document, 1):
                    rendered = work / f"{source.stem}-page-{page_number:03d}.png"
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    pixmap.save(str(rendered))
                    inputs.append({"path": rendered, "source_file": str(source), "page": page_number, "frame_time": None})
            finally:
                document.close()
        finally:
            if temp_context:
                temp_context.cleanup()

    # Video frames
    for video in config.video_files:
        inputs.extend(_extract_video_frames(video, work))

    return inputs


def draft_from_pi_result(result: dict) -> dict | None:
    """Recover a JSON draft when a model returns it instead of using write tools."""
    candidate = pi_json_result(result)
    return candidate if isinstance(candidate, dict) and all(key in candidate for key in ("outline", "primary_narration", "secondary_narration")) else None


def choose_folder() -> str:
    """Open a native folder picker when the current platform provides one."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        if os.name == "nt":
            root.attributes("-topmost", True)
        root.update()
        selected = filedialog.askdirectory(parent=root, title="Select product resource directory")
        root.destroy()
        return selected
    except Exception:  # noqa: BLE001 - try platform-native CLI pickers next.
        pass
    if os.name != "nt" and sys.platform == "darwin" and shutil.which("osascript"):
        script = 'POSIX path of (choose folder with prompt "Select product resource directory")'
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
        return result.stdout.strip()
    for command in (("zenity", "--file-selection", "--directory", "--title=Select product resource directory"), ("kdialog", "--getexistingdirectory", ".")):
        if shutil.which(command[0]):
            result = subprocess.run(list(command), capture_output=True, text=True, check=False)
            return result.stdout.strip()
    if os.name == "nt":
        script = "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='Select product resource directory'; if($d.ShowDialog() -eq 'OK'){ $d.SelectedPath }"
        result = subprocess.run(["powershell.exe", "-NoProfile", "-STA", "-Command", script], capture_output=True, text=True, check=False)
        return result.stdout.strip()
    return ""


def normalize_client_path(value: str) -> str:
    """Normalize a path submitted by the browser for the current platform.

    Some client code paths (and legacy browser state cached in localStorage)
    may send Windows-style backslash separators even when the Web GUI is
    running on macOS/Linux, where a backslash is just a literal filename
    character rather than a separator. Convert to forward slashes unless the
    value looks like a genuine Windows path (drive letter or UNC prefix),
    which PureWindowsPath-aware callers handle separately.
    """
    if os.name == "nt" or not value:
        return value
    if len(value) > 1 and value[1] == ":":  # e.g. C:\... — real Windows path
        return value
    if value.startswith("\\\\"):  # UNC path \\server\share
        return value
    return value.replace("\\", "/")


def select_product_root(value: str) -> str:
    """Make the selected product directory the session access boundary."""
    path = Path(normalize_client_path(value)).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"Product resource directory does not exist: {path}")
    os.environ["VIDEO_PROJECT_ROOT"] = str(path)
    return str(path)


def project_arg(query: dict[str, list[str]]) -> str:
    value = query.get("project", [""])[0].strip()
    if not value:
        raise ValueError("project is required")
    return select_product_root(value)


def validate_provider_token(provider: str, token: str) -> dict[str, object]:
    if provider == "dial":
        base = os.environ.get("DIAL_BASE_URL", "").rstrip("/")
        if not base:
            raise ValueError("Set DIAL_BASE_URL before validating a DIAL token.")
        request = urllib.request.Request(f"{base}/openai/models", headers={"Api-Key": token})
    elif provider == "elitea":
        base = os.environ.get("ELITEA_BASE_URL", "").rstrip("/")
        if not base:
            raise ValueError("Set ELITEA_BASE_URL before validating an ELITEA token.")
        request = urllib.request.Request(f"{base}/llm/v1/models", headers={"Authorization": f"Bearer {token}"})
    else:
        raise ValueError("Unsupported token provider")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        models = data.get("data", data.get("models", [])) if isinstance(data, dict) else []
        return {"valid": True, "provider": provider, "model_count": len(models) if isinstance(models, list) else 0}
    except urllib.error.HTTPError as error:
        return {"valid": False, "provider": provider, "error": f"HTTP {error.code}"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return {"valid": False, "provider": provider, "error": str(error)}


def subtitle_timestamp(value: str) -> float:
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return int(parts[0]) * 60 + float(parts[1])


def subtitle_time(seconds: float, separator: str = ",") -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_value, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds_value:02d}{separator}{milliseconds:03d}"


def parse_vtt_cues(content: str) -> list[dict[str, object]]:
    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", content):
        lines = [line.strip() for line in block.splitlines()]
        timing_index = next((index for index, line in enumerate(lines) if " --> " in line), -1)
        if timing_index < 0:
            continue
        start, end = lines[timing_index].split(" --> ", 1)
        cues.append({"start": subtitle_timestamp(start), "end": subtitle_timestamp(end.split()[0]), "text": " ".join(lines[timing_index + 1:])})
    return cues


def cues_to_srt(cues: list[dict[str, object]]) -> str:
    blocks = []
    for index, cue in enumerate(cues, 1):
        blocks.extend([str(index), f"{subtitle_time(float(cue['start']))} --> {subtitle_time(float(cue['end']))}", str(cue["text"]), ""])
    return "\n".join(blocks)


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(data)))
        handler.end_headers()
        handler.wfile.write(data)
    except OSError as error:
        # Browsers routinely cancel fetch/media requests during navigation,
        # polling refreshes, or range seeking. There is no socket left on which
        # an error response can be written in that case.
        if not client_disconnected(error):
            raise


def broadcast(payload: dict) -> None:
    message = json.dumps(payload, ensure_ascii=False)
    for client in list(WS_CLIENTS):
        try:
            client.send(message)
        except Exception:  # noqa: BLE001 - stale browser clients are disposable.
            WS_CLIENTS.discard(client)


def build_job(job_id: str, project: str, stop_after: str | None = None) -> None:
    JOBS[job_id]["status"] = "running"
    broadcast({"type": "job", "job": JOBS[job_id]})
    try:
        cancel_event = CANCEL_EVENTS[job_id]
        result = build_project(load_project(project), stop_after=stop_after, cancel_check=cancel_event.is_set)
        JOBS[job_id].update({"status": "completed", "result": result})
    except CancellationRequested as error:
        JOBS[job_id].update({"status": "cancelled", "error": str(error)})
        try:
            state_path = load_project(project).root / ".video-work" / "run-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"events": []}
            state["status"] = "cancelled"
            state["error"] = str(error)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            state.setdefault("events", []).append({"stage": state.get("stage", "unknown"), "status": "cancelled", "error": str(error), "at": state["updated_at"]})
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as state_error:  # noqa: BLE001
            JOBS[job_id]["state_error"] = str(state_error)
    except Exception as error:  # noqa: BLE001 - GUI must report the complete operation error.
        JOBS[job_id].update({"status": "failed", "error": str(error)})
        try:
            state_path = load_project(project).root / ".video-work" / "run-state.json"
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {"events": []}
            state["status"] = "failed"
            state["error"] = str(error)
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            state.setdefault("events", []).append({"stage": state.get("stage", "unknown"), "status": "failed", "error": str(error), "at": state["updated_at"]})
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as state_error:  # noqa: BLE001
            JOBS[job_id]["state_error"] = str(state_error)
    CANCEL_EVENTS.pop(job_id, None)
    broadcast({"type": "job", "job": JOBS[job_id]})


def watch_state(job_id: str, project: str) -> None:
    while JOBS.get(job_id, {}).get("status") in {"queued", "running"}:
        try:
            state = read_state(load_project(project).root)
            if state:
                broadcast({"type": "state", "state": state})
        except Exception:  # noqa: BLE001 - status monitoring must not stop a build.
            time.sleep(1.0)
            continue


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            requested_project = query.get("project", [""])[0].strip()
            if requested_project:
                select_product_root(requested_project)
            if parsed.path == "/api/service-log":
                try:
                    tail = int(query.get("tail", ["300"])[0])
                except (TypeError, ValueError):
                    tail = 300
                return json_response(self, {"text": read_service_log(tail), "tail": max(1, min(tail, 1000))})
            if parsed.path == "/api/service-status":
                runtime = {}
                try:
                    runtime = json.loads(RUNTIME_PATH.read_text(encoding="utf-8")) if RUNTIME_PATH.exists() else {}
                except (OSError, ValueError):
                    runtime = {}
                return json_response(self, {
                    **SERVICE_INFO,
                    **runtime,
                    "pid": os.getpid(),
                    "log_path": str(SERVICE_LOG_PATH),
                    "error_log_path": str(SERVICE_ERROR_LOG_PATH),
                    "pi_log_path": str(PI_LOG_PATH),
                    "pi": PI.status(),
                    "jobs": list(JOBS.values()),
                })
            if parsed.path == "/api/workspace":
                root = Path(os.environ.get("PVF_INSTALL_ROOT") or os.environ.get("VIDEO_PROJECT_ROOT") or Path.cwd()).resolve()
                default_project = root / "examples" / "mock-product"
                return json_response(self, {"root": str(root), "install_root": str(root), "default_project": str(default_project) if default_project.is_dir() else None, "os": "windows" if os.name == "nt" else "posix"})
            if parsed.path == "/api/browse":
                return json_response(self, {"path": choose_folder()})
            if parsed.path == "/api/config":
                config = load_project(project_arg(query))
                return json_response(self, {
                    "primary_language": config.primary_language,
                    "secondary_language": config.secondary_language,
                    "primary_voice": config.primary_voice,
                    "secondary_voice": config.secondary_voice,
                    "target_duration_seconds": config.target_duration_seconds,
                    "content_generation_provider": config.content_generation.provider,
                    "content_generation_model": config.content_generation.model,
                    "vision_enabled": config.vision.enabled,
                    "subscription_id": config.azure.subscription_id,
                    "speech_resource_id": config.azure.speech_resource_id,
                    "draft_instructions": config.draft_instructions,
                    "presentation_instructions": config.presentation_instructions,
                    "presentation_source": str(config.presentation.relative_to(config.root)) if config.presentation else "",
                    "presentation_sources": [str(path.relative_to(config.root)) for path in getattr(config, "presentation_sources", ())],
                    "presentation_template": str(config.presentation_template.relative_to(config.root)) if config.presentation_template else "",
                })
            if parsed.path == "/api/scan":
                config = load_project(project_arg(query))
                root = config.root
                resources = scan(root)
                # Source candidates exclude generated decks under the configured output directory.
                pptx_candidates = presentation_candidates(root, config.output_dir)
                pptx_source_candidates = [path for path in pptx_candidates if not is_presentation_template(path)]
                pptx_template_candidates = [path for path in pptx_candidates if is_presentation_template(path)]
                return json_response(self, {"project": str(root), "resources": resources, "pptx_candidates": pptx_candidates, "pptx_source_candidates": pptx_source_candidates, "pptx_template_candidates": pptx_template_candidates})
            if parsed.path == "/api/inspect":
                return json_response(self, inspect_project(load_project(project_arg(query))))
            if parsed.path == "/api/status":
                root = load_project(project_arg(query)).root
                state = read_state(root) or {"status": "not_started"}
                work = root / ".video-work"
                output_dir = root / "outputs"
                events_changed = False
                for event in state.get("events", []):
                    if event.get("status") == "running" and event.get("stage") != state.get("stage"):
                        event["status"] = "completed"
                        events_changed = True
                if state.get("stage") in {"video_rendering", "video_ready"} and all((output_dir / name).exists() for name in ("presentation-primary.mp4", "presentation-secondary.mp4", "presentation-dual.mp4")):
                    state["stage"] = "video_ready"
                    state["status"] = "completed"
                    state.pop("error", None)
                    video_files = {
                        "primary": str(output_dir / "presentation-primary.mp4"),
                        "secondary": str(output_dir / "presentation-secondary.mp4"),
                        "dual_track": str(output_dir / "presentation-dual.mp4"),
                    }
                    state.pop("video_files", None)
                    state["events"] = [event for event in state.setdefault("events", []) if event.get("stage") != "video_rendering" and not (event.get("stage") == "video_ready" and event.get("reconciled"))]
                    state["events"].append({"stage": "video_ready", "status": "completed", "video_files": video_files, "reconciled": True})
                    (work / "run-state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                if events_changed:
                    (work / "run-state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
                return json_response(self, state)
            if parsed.path == "/api/stages":
                config = load_project(project_arg(query))
                work = config.root / ".video-work"
                approvals_path = work / "approvals.json"
                approvals = json.loads(approvals_path.read_text(encoding="utf-8")) if approvals_path.exists() else {}
                presentation_path = config.presentation or config.output_dir / "presentation.pptx"
                presentation_generated = config.presentation is None
                discovered_presentations = presentation_candidates(config.root, config.output_dir)
                presentation_candidates_for_source = [path for path in discovered_presentations if not is_presentation_template(path)]
                presentation_source_required = len(presentation_candidates_for_source) > 1 and config.presentation is None and not getattr(config, "presentation_sources", ())
                pdf_path = config.output_dir / "presentation.pdf"
                actual_duration_seconds = None
                audio_durations = []
                for audio_path in (work / "primary.wav", work / "secondary.wav"):
                    if audio_path.exists():
                        with wave.open(str(audio_path), "rb") as audio:
                            audio_durations.append(audio.getnframes() / audio.getframerate())
                if audio_durations:
                    actual_duration_seconds = round(max(audio_durations), 2)
                duration_warning = bool(config.target_duration_seconds and actual_duration_seconds is not None and abs(actual_duration_seconds - config.target_duration_seconds) > max(10.0, config.target_duration_seconds * 0.2))
                # Estimate narration duration from draft text before audio is generated.
                # English TTS ~2.5 wps, Chinese TTS ~3.5 cps; use a combined rough heuristic.
                estimated_duration_seconds = None
                duration_estimate_warning = False
                draft_path = work / "content-draft.json"
                if draft_path.exists() and config.target_duration_seconds:
                    try:
                        draft_data = json.loads(draft_path.read_text(encoding="utf-8"))
                        total_chars = 0
                        for narr_key in ("primary_narration", "secondary_narration"):
                            for entry in draft_data.get(narr_key, []):
                                text = entry.get("text", "") or ""
                                # Count CJK chars separately (they speak slower in chars/sec)
                                cjk = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f' or '\uff00' <= ch <= '\uffef')
                                latin = len(text) - cjk
                                total_chars += cjk * 0.35 + latin * 0.18  # chars → words approx, then seconds
                        if total_chars > 0:
                            estimated_duration_seconds = round(total_chars, 1)
                            duration_estimate_warning = estimated_duration_seconds < config.target_duration_seconds * 0.8
                    except Exception:
                        pass
                vision_inputs = vision_input_count(config)
                state = read_state(config.root) or {}
                video_files_ready = all((config.output_dir / name).exists() for name in ("presentation-primary.mp4", "presentation-secondary.mp4", "presentation-dual.mp4"))
                build_running = bool(state.get("status") == "running" and state.get("stage") == "video_rendering" and not video_files_ready)
                audio_build_running = bool(state.get("status") == "running" and state.get("stage") in {"speech_synthesis", "subtitle_generation"})
                audio_exists = (work / "primary.wav").exists() and (work / "secondary.wav").exists()
                subtitles_exists = any(config.output_dir.glob("*.srt")) or any(config.output_dir.glob("*.vtt"))
                approval_status = {
                    stage: bool(item.get("approved")) and (
                        stage != "vision" or (work / "vision-analysis.json").exists()
                    )
                    for stage, item in approvals.items()
                }
                # Audio and subtitles are reviewable but auto-approved once generated.
                approval_status["audio"] = audio_exists
                approval_status["subtitles"] = subtitles_exists
                return json_response(self, {
                    "images": len(config.image_files),
                    "vision_input_count": vision_inputs,
                    "presentation_path": str(presentation_path.relative_to(config.root)),
                    "pdf_path": str(pdf_path.relative_to(config.root)),
                    "vision_enabled": config.vision.enabled,
                    "draft": (work / "content-draft.json").exists(),
                    "vision": (work / "vision-analysis.json").exists(),
                    "presentation": presentation_path.exists(),
                    "presentation_generated": presentation_generated and presentation_path.exists(),
                    "presentation_source_required": presentation_source_required,
                    "presentation_candidates": presentation_candidates_for_source,
                    "pdf": pdf_path.exists(),
                    "audio": audio_exists,
                    "actual_duration_seconds": actual_duration_seconds,
                    "target_duration_seconds": config.target_duration_seconds,
                    "duration_warning": duration_warning,
                    "estimated_duration_seconds": estimated_duration_seconds,
                    "duration_estimate_warning": duration_estimate_warning,
                    "review_audio_primary": str((work / "review-primary.wav").relative_to(config.root)),
                    "review_audio_secondary": str((work / "review-secondary.wav").relative_to(config.root)),
                    "subtitles": subtitles_exists,
                    "video": any(config.output_dir.glob("*.mp4")),
                    "build_running": build_running,
                    "audio_build_running": audio_build_running,
                    "approvals": approval_status,
                })
            if parsed.path == "/api/pi/status":
                return json_response(self, PI.status())
            if parsed.path == "/api/pi/internal-providers":
                return json_response(self, {"providers": pi_internal_provider_status(), "extension_providers": pi_extension_provider_status()})
            if parsed.path == "/api/pi/token-status":
                provider = query.get("provider", [""])[0].strip()
                if provider in PI_PROVIDER_IDS:
                    inventory = pi_internal_provider_status() + pi_extension_provider_status()
                    item = next(item for item in inventory if item["id"] == provider)
                    return json_response(self, {"provider": provider, "stored": item["configured"], "source": item["source"]})
                if provider not in {"dial", "elitea"}:
                    return json_response(self, {"provider": provider, "stored": False})
                stored = bool(os.environ.get(provider_token_name(provider)) or token_store_get(provider))
                return json_response(self, {"provider": provider, "stored": stored, "source": "secure_storage" if stored else "none"})
            if parsed.path in {"/api/pi/models", "/api/pi/model-catalog"}:
                project_path = query.get("project", [""])[0].strip()
                provider = query.get("provider", [""])[0].strip()
                if provider in {"dial", "elitea"} and not hydrate_provider_token(provider):
                    raise ValueError(f"{provider.upper()} token is not configured. Enter and validate a token first.")
                PI.start(project_path)
                result = PI.request({"type": "get_available_models"})
                models = result.get("data", {}).get("models", [])
                provider_filter = query.get("provider", [""])[0].strip()
                # pi-dial discovers its catalog asynchronously. The first RPC
                # request can therefore observe the empty seed list even though
                # the DIAL endpoint is reachable. Do not return that transient
                # state to the GUI; give the provider refresh a few seconds to
                # publish the discovered catalog.
                if provider_filter == "dial" and not any(item.get("provider") == "dial" for item in models):
                    deadline = time.monotonic() + 12
                    while time.monotonic() < deadline:
                        time.sleep(0.25)
                        result = PI.request({"type": "get_available_models"})
                        models = result.get("data", {}).get("models", [])
                        if any(item.get("provider") == "dial" for item in models):
                            break
                allowed = {"codemie", "codemie-cli", "dial", "elitea", *PI_PROVIDER_IDS}
                if provider_filter in allowed:
                    allowed = {provider_filter}
                return json_response(self, {
                    "models": [
                        {
                            "provider": item.get("provider"),
                            "id": item.get("id"),
                            "name": item.get("name", item.get("id")),
                            "api": item.get("api"),
                            "input": item.get("input", []),
                            "reasoning": item.get("reasoning", False),
                            "cost": item.get("cost", {}),
                            "context_window": item.get("contextWindow"),
                            "max_tokens": item.get("maxTokens"),
                            "capabilities": item.get("capabilities", {}),
                        }
                        for item in models
                        if item.get("provider") in allowed
                    ],
                    "status": PI.status(),
                })
            if parsed.path == "/api/azure/status":
                return json_response(self, login_status())
            if parsed.path == "/api/azure/subscriptions":
                project_path = query.get("project", [""])[0].strip()
                refresh = query.get("refresh", ["0"])[0].lower() in {"1", "true", "yes"}
                cache_path = ROOT / ".video-work" / "subscriptions-cache.json"
                if not refresh and cache_path.exists():
                    cached = json.loads(cache_path.read_text(encoding="utf-8"))
                    if time.time() - float(cached.get("loaded_at", 0)) < 3600:
                        return json_response(self, {"subscriptions": cached.get("subscriptions", []), "cached": True})
                config = load_project(project_path) if project_path else SimpleNamespace(root=ROOT, azure=SimpleNamespace(checkout_dir="vendor/azure-mcp"))
                subscriptions = account(config)
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps({"subscriptions": subscriptions, "loaded_at": time.time()}, ensure_ascii=False), encoding="utf-8")
                return json_response(self, {"subscriptions": subscriptions, "cached": False})
            if parsed.path == "/api/azure/resources":
                project_path = query.get("project", [""])[0].strip()
                config = load_project(project_path) if project_path else SimpleNamespace(root=ROOT, azure=SimpleNamespace(checkout_dir="vendor/azure-mcp", subscription_id=None))
                subscription = query.get("subscription", [None])[0]
                refresh = query.get("refresh", ["0"])[0].lower() in {"1", "true", "yes"}
                cache_path = ROOT / ".video-work" / "azure-resource-cache.json"
                if not refresh and cache_path.exists():
                    cached = json.loads(cache_path.read_text(encoding="utf-8"))
                    if cached.get("subscription_id") == subscription:
                        return json_response(self, {"resources": cached.get("resources", []), "count": len(cached.get("resources", [])), "cached": True, "message": "Speech resources loaded from local cache."})
                resources = speech_resources(config, subscription)
                payload = [resource.__dict__ for resource in resources]
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps({"subscription_id": subscription, "resources": payload, "loaded_at": time.time()}, ensure_ascii=False), encoding="utf-8")
                return json_response(self, {
                    "resources": payload,
                    "count": len(payload),
                    "cached": False,
                    "message": "Speech resources found." if payload else "No Azure Speech resource was found. Sign in to the Azure Portal to create one, then refresh Speech resources.",
                })
            if parsed.path == "/api/azure/voices":
                project_path = query.get("project", [""])[0].strip()
                resource_id = query.get("resource_id", [""])[0]
                subscription = query.get("subscription", [None])[0]
                refresh = query.get("refresh", ["0"])[0].lower() in {"1", "true", "yes"}
                if project_path:
                    config = load_project(project_path)
                    subscription = subscription or config.azure.subscription_id
                    azure_config = replace(config.azure, speech_resource_id=resource_id, subscription_id=subscription)
                    speech_config = replace(config, azure=azure_config)
                else:
                    speech_config = SimpleNamespace(root=ROOT, azure=SimpleNamespace(checkout_dir="vendor/azure-mcp", speech_resource_id=resource_id, subscription_id=subscription))
                # Keep one user-level project cache so loading a product directory
                # after Azure setup does not trigger the same catalog request again.
                cache_path = ROOT / ".video-work" / "voice-catalog.json"
                if not refresh and cache_path.exists():
                    cached = json.loads(cache_path.read_text(encoding="utf-8"))
                    if cached.get("resource_id") == resource_id and cached.get("subscription_id") == subscription:
                        return json_response(self, {"resource": cached.get("resource", {}), "voices": cached.get("voices", []), "cached": True, "loaded_at": cached.get("loaded_at")})
                resource, key, voices = resolve_speech(speech_config)
                del key
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps({"resource_id": resource.id, "subscription_id": subscription, "resource": resource.__dict__, "voices": voices, "loaded_at": time.time()}, ensure_ascii=False), encoding="utf-8")
                return json_response(self, {"resource": resource.__dict__, "voices": voices, "cached": False, "loaded_at": time.time()})
            if parsed.path == "/api/draft":
                root = load_project(project_arg(query)).root
                draft = root / ".video-work" / "content-draft.json"
                return json_response(self, json.loads(draft.read_text(encoding="utf-8")) if draft.exists() else {"status": "missing"})
            if parsed.path == "/api/vision/report":
                config = load_project(project_arg(query))
                report = config.root / ".video-work" / "vision-analysis.json"
                return json_response(self, normalize_vision_report(config.root, json.loads(report.read_text(encoding="utf-8"))) if report.exists() else {"status": "missing"})
            if parsed.path == "/api/subtitles":
                config = load_project(project_arg(query))
                track = query.get("track", ["bilingual"])[0]
                if track not in {"primary", "secondary", "bilingual"}:
                    raise ValueError("track must be primary, secondary, or bilingual")
                path = config.output_dir / f"presentation-{track}.vtt"
                return json_response(self, {"track": track, "content": path.read_text(encoding="utf-8") if path.exists() else ""})
            if parsed.path == "/api/text":
                config = load_project(project_arg(query))
                relative = Path(query.get("path", [""])[0])
                file_path = (config.root / relative).resolve()
                if not file_path.is_file() or not file_path.is_relative_to(config.root.resolve()):
                    return json_response(self, {"error": "file not found"}, 404)
                text = _read_document(file_path)
                return json_response(self, {"path": str(relative), "text": text[:200_000], "truncated": len(text) > 200_000})
            if parsed.path == "/api/file":
                config = load_project(project_arg(query))
                relative = Path(query.get("path", [""])[0])
                file_path = (config.root / relative).resolve()
                if not file_path.is_file() or not file_path.is_relative_to(config.root.resolve()):
                    return json_response(self, {"error": "file not found"}, 404)
                size = file_path.stat().st_size
                start, end = 0, size - 1
                range_header = self.headers.get("Range", "")
                if range_header.startswith("bytes="):
                    range_value = range_header.removeprefix("bytes=").split(",", 1)[0]
                    first, _, last = range_value.partition("-")
                    if first:
                        start = int(first)
                        end = int(last) if last else size - 1
                    elif last:
                        start = max(0, size - int(last))
                    if start < 0 or start >= size or end < start:
                        self.send_error(416, "Requested range not satisfiable")
                        return
                    end = min(end, size - 1)
                length = end - start + 1
                self.send_response(206 if range_header.startswith("bytes=") else 200)
                content_type = {".srt": "text/plain; charset=utf-8", ".vtt": "text/vtt; charset=utf-8"}.get(file_path.suffix.lower(), mimetypes.guess_type(file_path.name)[0] or "application/octet-stream")
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(length))
                if range_header.startswith("bytes="):
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                with file_path.open("rb") as stream:
                    stream.seek(start)
                    remaining = length
                    while remaining:
                        chunk = stream.read(min(1024 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                return
            file_path = WEB_ROOT / ("index.html" if parsed.path == "/" else parsed.path.lstrip("/"))
            if not file_path.exists() or not file_path.is_file() or not file_path.resolve().is_relative_to(WEB_ROOT.resolve()):
                return json_response(self, {"error": "not found"}, 404)
            data = file_path.read_bytes()
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except Exception as error:  # noqa: BLE001 - GUI must report request failures as JSON.
            if client_disconnected(error):
                return
            json_response(self, {"error": str(error)}, 400)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            project = str(body.get("project", "")).strip()
            if project:
                project = select_product_root(project)
            if parsed.path == "/api/restart":
                if self.client_address[0] not in {"127.0.0.1", "::1"}:
                    raise PermissionError("Restart is only available from localhost.")
                for event in CANCEL_EVENTS.values():
                    event.set()
                PI.stop()
                pid = restart_service_process()
                response = json_response(self, {"restarting": True, "pid": pid, "message": "Web GUI restart requested."})
                def restart_server() -> None:
                    time.sleep(0.1)
                    if HTTP_SERVER is not None:
                        HTTP_SERVER.shutdown()
                threading.Thread(target=restart_server, daemon=True).start()
                return response
            if parsed.path == "/api/shutdown":
                if self.client_address[0] not in {"127.0.0.1", "::1"}:
                    raise PermissionError("Shutdown is only available from localhost.")
                for event in CANCEL_EVENTS.values():
                    event.set()
                PI.stop()
                RUNTIME_PATH.unlink(missing_ok=True)
                response = json_response(self, {"stopping": True, "message": "Web GUI shutdown requested."})
                def stop_server() -> None:
                    time.sleep(0.1)
                    if HTTP_SERVER is not None:
                        HTTP_SERVER.shutdown()
                threading.Thread(target=stop_server, daemon=True).start()
                return response
            if parsed.path == "/api/workspace":
                workspace = str(body.get("root", "")).strip()
                if not workspace:
                    raise ValueError("workspace root is required")
                root = Path(normalize_client_path(workspace)).expanduser().resolve()
                if not root.is_dir():
                    raise ValueError(f"Workspace root does not exist: {root}")
                os.environ["VIDEO_PROJECT_ROOT"] = str(root)
                return json_response(self, {"root": str(root), "saved_for_session": True})
            if parsed.path == "/api/azure/voice-preview":
                config = load_project(project)
                language = str(body.get("language", "")).strip()
                voice = str(body.get("voice", "")).strip()
                resource_id = str(body.get("resource_id", "")).strip() or config.azure.speech_resource_id
                if not language or not voice:
                    raise ValueError("language and voice are required")
                if not resource_id:
                    raise ValueError("Select a Speech resource before previewing a voice")
                subscription = str(body.get("subscription", "")).strip() or config.azure.subscription_id
                speech_config = replace(config, azure=replace(config.azure, speech_resource_id=resource_id, subscription_id=subscription))
                resource, key, _ = resolve_speech(speech_config)
                preview_text = str(body.get("text", "")).strip()
                if not preview_text:
                    preview_text = "这是所选语音的试听。" if language.lower().startswith(("zh", "ja", "ko")) else "This is a preview of the selected voice."
                preview_dir = config.root / ".video-work" / "voice-previews"
                preview_path = synthesize_voice_preview(preview_text, voice, language, key, resource.location, preview_dir / f"preview-{uuid.uuid4().hex}.wav")
                previews = sorted(preview_dir.glob("preview-*.wav"), key=lambda path: path.stat().st_mtime, reverse=True)
                for old_path in previews[8:]:
                    old_path.unlink(missing_ok=True)
                return json_response(self, {"path": str(preview_path.relative_to(config.root)).replace("\\", "/"), "text": preview_text, "voice": voice, "language": language})
            if parsed.path == "/api/pi/start":
                PI.start(project)
                result = PI.status()
                result["started"] = True
                return json_response(self, result)
            if parsed.path == "/api/pi/stop":
                PI.stop()
                return json_response(self, {"running": False, "stopped": True, "codemie_authenticated": False})
            if parsed.path == "/api/pi/login":
                result = codemie_login(project)
                return json_response(self, {"status": "login_started", "pi": result, **PI.status()})
            if parsed.path == "/api/pi/internal-login":
                provider = str(body.get("provider", "")).strip().lower()
                result = pi_internal_login(provider, project)
                return json_response(self, {"status": "login_started", "provider": provider, "pi": result, **PI.status(), "providers": pi_internal_provider_status()})
            if parsed.path == "/api/pi/logout":
                result = codemie_logout(project)
                return json_response(self, {"status": "logged_out", "pi": result, **PI.status()})
            if parsed.path == "/api/pi/usage":
                provider = str(body.get("provider", "openai")).strip()
                if provider in PI_PROVIDER_IDS:
                    inventory = pi_internal_provider_status() + pi_extension_provider_status()
                    item = next(item for item in inventory if item["id"] == provider)
                    if not item["configured"]:
                        raise ValueError(f"{provider} is not authenticated or its extension is not installed.")
                    return json_response(self, {"provider": provider, "supported": False, "usage": [], "message": "Pi does not expose balance or usage data for this provider.", "status": PI.status()})
                if provider in {"dial", "elitea"}:
                    if not hydrate_provider_token(provider):
                        raise ValueError(f"{provider.upper()} token is not configured.")
                elif not PI.status()["codemie_authenticated"]:
                    raise ValueError("CodeMie is not authenticated.")
                PI.start(project)
                command = "/elitea-usage" if provider == "elitea" else "/dial-usage" if provider == "dial" else "/codemie-usage"
                result = PI.request({"type": "prompt", "message": command}, collect_notifications=True)
                return json_response(self, {"provider": provider, "usage": result.get("notifications", []), "status": PI.status()})
            if parsed.path == "/api/pi/token":
                provider = str(body.get("provider", "")).strip().lower()
                token = str(body.get("token", "")).strip()
                if provider in PI_PROVIDER_IDS:
                    result = save_pi_internal_token(provider, token, bool(body.get("remember", True)))
                    PI.start(project)
                    return json_response(self, {**result, "status": "authenticated", **PI.status()})
                if not token:
                    raise ValueError("Token is required")
                result = validate_provider_token(provider, token)
                if not result.get("valid"):
                    return json_response(self, result, 401)
                PI.set_provider_token(provider, token)
                persistence_warning = ""
                if bool(body.get("remember", True)):
                    try:
                        token_store_set(provider, token)
                    except Exception as error:  # noqa: BLE001
                        persistence_warning = f"Token validated for this session but secure persistence failed: {error}"
                else:
                    token_store_delete(provider)
                PI.start(project)
                return json_response(self, {**result, "status": "authenticated", "token_persisted": not persistence_warning, "warning": persistence_warning, **PI.status()})
            if parsed.path == "/api/pi/model-test":
                provider = str(body.get("provider", "")).strip().lower()
                model_id = str(body.get("model_id", "")).strip()
                result = pi_model_test(provider, model_id, project)
                return json_response(self, {**result, "status": PI.status()})
            if parsed.path == "/api/pi/model":
                PI.start(project)
                provider = str(body.get("provider", "openai"))
                if provider in {"dial", "elitea"} and not hydrate_provider_token(provider):
                    raise ValueError(f"{provider.upper()} token is not configured. Validate the token first.")
                model_id = str(body.get("model_id", "")).strip()
                if not model_id:
                    raise ValueError("model_id is required")
                result = PI.request({"type": "set_model", "provider": provider, "modelId": model_id})
                return json_response(self, {"selected": model_id, "provider": provider, "pi": result})
            if parsed.path == "/api/pi/draft":
                PI.start(project)
                provider = str(body.get("provider", "openai")).strip()
                if provider in {"dial", "elitea"} and not PI.provider_env.get({"dial": "DIAL_API_KEY", "elitea": "ELITEA_API_TOKEN"}[provider]):
                    raise ValueError(f"{provider.upper()} token is not authenticated. Validate the token first.")
                if provider in PI_PROVIDER_IDS:
                    inventory = pi_internal_provider_status() + pi_extension_provider_status()
                    internal = next(item for item in inventory if item["id"] == provider)
                    if not internal["configured"]:
                        raise ValueError(f"{provider} is not authenticated or its extension is not installed. Login or save a token first.")
                if provider in {"codemie", "codemie-cli"} and not PI.status()["codemie_authenticated"]:
                    raise ValueError("CodeMie is not authenticated. Login CodeMie SSO first.")
                model_id = str(body.get("model_id", "")).strip()
                if model_id:
                    PI.request({"type": "set_model", "provider": provider, "modelId": model_id})
                approvals = load_project(project).root / ".video-work" / "approvals.json"
                approval_data = json.loads(approvals.read_text(encoding="utf-8")) if approvals.exists() else {}
                for downstream in ("draft", "presentation", "audio", "subtitles", "video"):
                    approval_data.pop(downstream, None)
                approvals.parent.mkdir(parents=True, exist_ok=True)
                approvals.write_text(json.dumps(approval_data, indent=2), encoding="utf-8")
                draft_config = load_project(project)
                duration_instruction = (
                    f"The requested target duration is {draft_config.target_duration_seconds:.0f} seconds. Plan enough substantive narration and outline content to approach that duration at a natural speaking rate; do not slow the speech artificially. "
                    if draft_config.target_duration_seconds else
                    "No target duration is set; use the natural narration duration. "
                )
                # The GUI sends the current textarea value with the request so
                # users do not have to save the whole configuration before trying
                # a one-off prompt. If the field is omitted (for example, from a
                # CLI/API client), keep using the configured instructions.
                if "draft_instructions" in body:
                    extra_instructions = str(body.get("draft_instructions") or "").strip()
                else:
                    extra_instructions = draft_config.draft_instructions.strip()
                _NL = chr(10)
                extra_clause = (_NL + _NL + "Additional instructions from the user:" + _NL + extra_instructions) if extra_instructions else ""
                prompt = (
                    f"Work on the product video project at {project}. Inspect its product materials, documents, tables, and images. "
                    + duration_instruction
                    + "Produce a factual structured JSON draft with exactly these top-level keys: outline, primary_narration, and secondary_narration. "
                    "The primary language is English and the configured secondary language must be used. "
                    f"Write the complete draft to {project}/.video-work/content-draft.json, "
                    f"write the primary narration array to {project}/.video-work/narration-primary.json, "
                    f"and write the secondary narration array to {project}/.video-work/narration-secondary.json. "
                    "Create the .video-work directory if necessary. Do not build the PPT or video yet. "
                    "If you cannot write files with tools, return the complete JSON draft in your final response inside a json code block."
                    + extra_clause
                )
                result = PI.request({"type": "prompt", "message": prompt}, wait_for_agent=True)
                draft_path = load_project(project).root / ".video-work" / "content-draft.json"
                if not draft_path.exists():
                    recovered = draft_from_pi_result(result)
                    if recovered is None:
                        retry = PI.request({"type": "prompt", "message": "Your previous turn did not create the requested files. Return ONLY a complete valid JSON object with exactly these keys: outline, primary_narration, secondary_narration. Do not use Markdown and do not explain anything."}, wait_for_agent=True)
                        result["retry"] = retry
                        recovered = draft_from_pi_result(retry)
                    if recovered is not None:
                        work = draft_path.parent
                        work.mkdir(parents=True, exist_ok=True)
                        draft_path.write_text(json.dumps(recovered, ensure_ascii=False, indent=2), encoding="utf-8")
                        (work / "narration-primary.json").write_text(json.dumps(recovered["primary_narration"], ensure_ascii=False, indent=2), encoding="utf-8")
                        (work / "narration-secondary.json").write_text(json.dumps(recovered["secondary_narration"], ensure_ascii=False, indent=2), encoding="utf-8")
                    else:
                        debug_path = draft_path.parent / "pi-draft-response.json"
                        debug_path.parent.mkdir(parents=True, exist_ok=True)
                        debug_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                        # Surface the Pi agent error (e.g. unsupported API) if
                        # no file was written and no JSON was recovered.
                        for attempt_key in (None, "retry"):
                            attempt = result.get(attempt_key) if attempt_key else result
                            if isinstance(attempt, dict) and "agent_end" in attempt:
                                _raise_agent_error(attempt["agent_end"])
                        raise RuntimeError(
                            "Pi finished without creating .video-work/content-draft.json or "
                            "returning valid JSON after one retry. "
                            "Diagnostic response: .video-work/pi-draft-response.json"
                        )
                return json_response(self, {"status": "completed", "message": "Draft generation completed. Review the draft before building.", "draft": str(draft_path), "pi": result})
            if parsed.path == "/api/azure/subscriptions/cache-clear":
                (ROOT / ".video-work" / "subscriptions-cache.json").unlink(missing_ok=True)
                return json_response(self, {"cleared": True})
            if parsed.path == "/api/azure/login":
                result = login()
                return json_response(self, {"status": result.get("status", "logged_in"), "accounts": result})
            if parsed.path == "/api/azure/logout":
                return json_response(self, logout())
            if parsed.path == "/api/cancel":
                job_id = str(body.get("job_id", "")).strip()
                if job_id and job_id in CANCEL_EVENTS:
                    CANCEL_EVENTS[job_id].set()
                    JOBS[job_id]["cancel_requested"] = True
                    broadcast({"type": "job", "job": JOBS[job_id]})
                    return json_response(self, {"status": "cancelling", "job_id": job_id})
                # Draft/Vision calls use the Pi RPC synchronously. Stopping Pi
                # interrupts the active request; the request handler reports it
                # as cancelled and a later operation starts a fresh Pi process.
                PI.stop()
                return json_response(self, {"status": "cancelling", "project": project})
            if parsed.path == "/api/open-output":
                config = load_project(project)
                config.output_dir.mkdir(parents=True, exist_ok=True)
                if os.name == "nt":
                    subprocess.Popen(["explorer.exe", "/root,", str(config.output_dir)])
                elif shutil.which("xdg-open"):
                    subprocess.Popen(["xdg-open", str(config.output_dir)])
                elif shutil.which("open"):
                    subprocess.Popen(["open", str(config.output_dir)])
                else:
                    raise RuntimeError("No local file manager opener was found")
                return json_response(self, {"opened": str(config.output_dir)})
            if parsed.path in {"/api/build", "/api/build-ppt", "/api/build-audio"}:
                load_project(project)
                stop_after = {"/api/build-ppt": "presentation", "/api/build-audio": "audio"}.get(parsed.path)

                job_id = uuid.uuid4().hex
                JOBS[job_id] = {"id": job_id, "status": "queued", "project": project, "stage": stop_after or "video"}
                CANCEL_EVENTS[job_id] = threading.Event()
                EXECUTOR.submit(build_job, job_id, project, stop_after)
                threading.Thread(target=watch_state, args=(job_id, project), daemon=True).start()
                return json_response(self, JOBS[job_id], 202)
            if parsed.path == "/api/subtitles":
                config = load_project(project)
                track = str(body.get("track", "bilingual"))
                content = str(body.get("content", ""))
                if track not in {"primary", "secondary", "bilingual"}:
                    raise ValueError("track must be primary, secondary, or bilingual")
                cues = parse_vtt_cues(content)
                if not cues:
                    raise ValueError("Subtitle content must contain at least one valid WebVTT cue")
                output_dir = config.output_dir
                output_dir.mkdir(parents=True, exist_ok=True)
                vtt_path = output_dir / f"presentation-{track}.vtt"
                srt_path = output_dir / f"presentation-{track}.srt"
                vtt_path.write_text(content if content.startswith("WEBVTT") else "WEBVTT\n\n" + content, encoding="utf-8")
                srt_path.write_text(cues_to_srt(cues), encoding="utf-8")
                approvals = config.root / ".video-work" / "approvals.json"
                data = json.loads(approvals.read_text(encoding="utf-8")) if approvals.exists() else {}
                data.pop("video", None)
                approvals.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return json_response(self, {"saved": str(vtt_path), "srt": str(srt_path), "cues": len(cues)})
            if parsed.path == "/api/vision/report":
                config = load_project(project)
                report = body.get("report")
                if not isinstance(report, list) or not all(isinstance(item, dict) for item in report):
                    raise ValueError("vision report must be a list of objects")
                work = config.root / ".video-work"
                work.mkdir(parents=True, exist_ok=True)
                report = normalize_vision_report(config.root, report)
                (work / "vision-analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                approvals = work / "approvals.json"
                data = json.loads(approvals.read_text(encoding="utf-8")) if approvals.exists() else {}
                for stage in ("vision", "draft", "presentation", "audio", "subtitles", "video"):
                    data.pop(stage, None)
                approvals.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return json_response(self, {"saved": str(work / "vision-analysis.json"), "images": len(report)})
            if parsed.path == "/api/vision":
                config = load_project(project)
                if not config.vision.enabled:
                    raise ValueError("Enable Vision image analysis and save configuration first.")
                PI.start(project)
                vision_provider = config.content_generation.provider
                if vision_provider in {"dial", "elitea"}:
                    if not PI.provider_env.get({"dial": "DIAL_API_KEY", "elitea": "ELITEA_API_TOKEN"}[vision_provider]):
                        raise ValueError(f"{vision_provider.upper()} token is not authenticated. Validate the token before Vision analysis.")
                elif vision_provider in PI_PROVIDER_IDS:
                    inventory = pi_internal_provider_status() + pi_extension_provider_status()
                    internal = next(item for item in inventory if item["id"] == vision_provider)
                    if not internal["configured"]:
                        raise ValueError(f"{vision_provider} is not authenticated or its extension is not installed. Login or save a token before Vision analysis.")
                elif not PI.status()["codemie_authenticated"]:
                    raise ValueError("CodeMie is not authenticated. Login before analyzing images.")
                # The GUI normally selects the model through /api/pi/model. Set
                # the persisted model again here so Vision also works after a
                # fresh Pi restart or when the request comes from another client.
                if config.content_generation.model:
                    PI.request({"type": "set_model", "provider": vision_provider, "modelId": config.content_generation.model})
                results = []
                for item in vision_input_pages(config):
                    image = item["path"]
                    if image.stat().st_size > config.vision.max_image_bytes:
                        raise ValueError(f"Vision input exceeds size limit: {image}")
                    mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
                    source_file = Path(item["source_file"])
                    if item.get("frame_time") is not None:
                        source_description = f" (frame at {item['frame_time']} of {source_file.name})"
                    elif item["page"] and source_file.suffix.lower() in {".pptx", ".ppt"}:
                        source_description = f" (slide {item['page']} of {source_file.name})"
                    elif item["page"]:
                        source_description = f" (page {item['page']} of {source_file.name})"
                    else:
                        source_description = ""
                    prompt = f"Analyze this product image{source_description}. Return JSON only with keys type, description, visible_text, key_points, alt_text, suggested_slide, confidence. Do not invent facts that are not visible."
                    result = PI.request({"type": "prompt", "message": prompt, "images": [{"type": "image", "data": base64.b64encode(image.read_bytes()).decode("ascii"), "mimeType": mime}]}, wait_for_agent=True)
                    analysis = pi_json_result(result)
                    if not isinstance(analysis, dict):
                        raise TypeError(f"Vision model did not return a JSON object for {image}")
                    analysis["file"] = str(image)
                    analysis["source_file"] = item["source_file"]
                    if item["page"]:
                        analysis["page"] = item["page"]
                    results.append(analysis)
                work = config.root / ".video-work"
                work.mkdir(parents=True, exist_ok=True)
                report = normalize_vision_report(config.root, results)
                report_path = work / "vision-analysis.json"
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                approvals = work / "approvals.json"
                data = json.loads(approvals.read_text(encoding="utf-8")) if approvals.exists() else {}
                for stage in ("vision", "presentation", "audio", "subtitles", "video"):
                    data.pop(stage, None)
                approvals.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return json_response(self, {"report": str(report), "images": len(results)})
            if parsed.path == "/api/approve":
                config = load_project(project)
                stage = str(body.get("stage", "")).strip()
                if stage not in {"vision", "draft", "presentation"}:
                    raise ValueError("stage must be vision, draft, or presentation")
                approvals = config.root / ".video-work" / "approvals.json"
                data = json.loads(approvals.read_text(encoding="utf-8")) if approvals.exists() else {}
                data[stage] = {"approved": True, "at": time.time()}
                approvals.parent.mkdir(parents=True, exist_ok=True)
                approvals.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return json_response(self, data)
            if parsed.path == "/api/regenerate":
                config = load_project(project)
                stage = str(body.get("stage", "")).strip()
                order = ["draft", "presentation", "audio", "subtitles", "video"]
                if stage not in order:
                    raise ValueError("stage must be draft, presentation, audio, or video")
                approvals = config.root / ".video-work" / "approvals.json"
                data = json.loads(approvals.read_text(encoding="utf-8")) if approvals.exists() else {}
                for downstream in order[order.index(stage):]:
                    data.pop(downstream, None)
                approvals.parent.mkdir(parents=True, exist_ok=True)
                approvals.write_text(json.dumps(data, indent=2), encoding="utf-8")
                work = config.root / ".video-work"
                if stage == "presentation":
                    for path in (work / "generated-presentation.pptx", config.output_dir / "presentation.pptx", work / "generated-presentation.pdf", config.output_dir / "presentation.pdf"):
                        path.unlink(missing_ok=True)
                elif stage == "audio":
                    for path in (work / "audio-primary", work / "audio-secondary", work / "primary.wav", work / "secondary.wav", work / "review-primary.wav", work / "review-secondary.wav", work / "primary-manifest.json", work / "secondary-manifest.json"):
                        if path.is_dir():
                            shutil.rmtree(path, ignore_errors=True)
                        else:
                            path.unlink(missing_ok=True)
                elif stage == "video" and config.output_dir.exists():
                    shutil.rmtree(config.output_dir, ignore_errors=True)
                return json_response(self, {"regenerating": stage, "message": f"{stage} outputs and downstream approvals were cleared. Run Build video to regenerate."})
            if parsed.path == "/api/draft":
                config = load_project(project)
                draft = body.get("draft")
                if not isinstance(draft, dict):
                    raise ValueError("draft must be a JSON object")
                for key in ("outline", "primary_narration", "secondary_narration"):
                    if key not in draft:
                        raise ValueError(f"draft is missing {key}")
                work = config.root / ".video-work"
                work.mkdir(parents=True, exist_ok=True)
                (work / "content-draft.json").write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
                (work / "narration-primary.json").write_text(json.dumps(draft["primary_narration"], ensure_ascii=False, indent=2), encoding="utf-8")
                (work / "narration-secondary.json").write_text(json.dumps(draft["secondary_narration"], ensure_ascii=False, indent=2), encoding="utf-8")
                approvals = work / "approvals.json"
                data = json.loads(approvals.read_text(encoding="utf-8")) if approvals.exists() else {}
                for stage in ("draft", "presentation", "audio", "video"):
                    data.pop(stage, None)
                approvals.write_text(json.dumps(data, indent=2), encoding="utf-8")
                return json_response(self, {"saved": str(work / "content-draft.json")})
            if parsed.path == "/api/draft-instructions":
                config = load_project(project)
                raw, _, _ = project_settings(config.root)
                instructions = str(body.get("draft_instructions") or "").strip()
                if instructions:
                    raw["draft_instructions"] = instructions
                else:
                    raw.pop("draft_instructions", None)
                path = save_project_settings(config.root, raw)
                return json_response(self, {"saved": str(path), "message": "Draft prompt saved."})
            if parsed.path == "/api/presentation-instructions":
                config = load_project(project)
                raw, _, _ = project_settings(config.root)
                instructions = str(body.get("presentation_instructions") or "").strip()
                if instructions:
                    raw["presentation_instructions"] = instructions
                else:
                    raw.pop("presentation_instructions", None)
                path = save_project_settings(config.root, raw)
                return json_response(self, {"saved": str(path), "message": "PPT generation prompt saved."})
            if parsed.path == "/api/config":
                config = load_project(project)
                raw, _, _ = project_settings(config.root)
                raw.setdefault("azure", {})["subscription_id"] = body.get("subscription_id") or raw.get("azure", {}).get("subscription_id")
                raw.setdefault("azure", {})["speech_resource_id"] = body.get("speech_resource_id") or raw.get("azure", {}).get("speech_resource_id")
                raw.setdefault("vision_analysis", {})["enabled"] = bool(body.get("vision_enabled", raw.get("vision_analysis", {}).get("enabled", True)))
                if body.get("llm_provider"):
                    raw.setdefault("content_generation", {})["provider"] = str(body["llm_provider"])
                if body.get("llm_model"):
                    raw.setdefault("content_generation", {})["model"] = str(body["llm_model"])
                    raw.setdefault("vision_analysis", {})["model"] = str(body["llm_model"])
                raw["primary_language"] = str(body.get("primary_language", raw.get("primary_language", "en-US")))
                raw["secondary_language"] = str(body.get("secondary_language", raw.get("secondary_language", "zh-CN")))
                raw.setdefault("voices", {})["primary"] = str(body.get("primary_voice", raw.get("voices", {}).get("primary", "en-US-JennyNeural")))
                raw.setdefault("voices", {})["secondary"] = str(body.get("secondary_voice", raw.get("voices", {}).get("secondary", "zh-CN-YunyangNeural")))
                duration = str(body.get("target_duration_seconds", "")).strip()
                if duration:
                    try:
                        duration_value = float(duration)
                    except ValueError as error:
                        raise ValueError("target_duration_seconds must be numeric") from error
                    if duration_value < 30:
                        raise ValueError("target_duration_seconds must be at least 30 seconds")
                    raw.setdefault("output", {})["target_duration_seconds"] = duration_value
                else:
                    raw.setdefault("output", {}).pop("target_duration_seconds", None)
                instructions = str(body.get("draft_instructions", "")).strip()
                if instructions:
                    raw["draft_instructions"] = instructions
                else:
                    raw.pop("draft_instructions", None)
                presentation_instructions = str(body.get("presentation_instructions", raw.get("presentation_instructions", ""))).strip()
                if presentation_instructions:
                    raw["presentation_instructions"] = presentation_instructions
                else:
                    raw.pop("presentation_instructions", None)
                source_ppt = str(body.get("presentation_source", "")).strip()
                ppt_tpl = str(body.get("presentation_template", "")).strip()
                source_ppt_values = body.get("presentation_sources") or []
                if isinstance(source_ppt_values, str):
                    source_ppt_values = [source_ppt_values]
                source_ppt_values = [str(value).strip() for value in source_ppt_values if str(value).strip()]
                if source_ppt_values:
                    for source_ppt_value in source_ppt_values:
                        source_path = config.root / source_ppt_value
                        if not source_path.is_file() or source_path.suffix.lower() not in {".pptx", ".ppt"}:
                            raise ValueError(f"Source PPT not found or not a .pptx/.ppt file: {source_ppt_value}")
                    if len(source_ppt_values) == 1:
                        raw.setdefault("sources", {})["presentation"] = source_ppt_values[0]
                        raw.setdefault("sources", {}).pop("presentation_sources", None)
                        source_ppt = source_ppt_values[0]
                    else:
                        raw.setdefault("sources", {})["presentation_sources"] = source_ppt_values
                        raw.setdefault("sources", {}).pop("presentation", None)
                        source_ppt = ""
                elif source_ppt:
                    raw.setdefault("sources", {})["presentation"] = source_ppt
                    raw.setdefault("sources", {}).pop("presentation_sources", None)
                else:
                    raw.setdefault("sources", {}).pop("presentation", None)
                    raw.setdefault("sources", {}).pop("presentation_sources", None)

                if ppt_tpl and any(ppt_tpl.replace("\\", "/") == value.replace("\\", "/") for value in ([source_ppt] if source_ppt else source_ppt_values)):
                    raise ValueError("The source PPT and slide template must be different files.")
                if ppt_tpl:
                    tpl_path = config.root / ppt_tpl
                    if not tpl_path.exists() or tpl_path.suffix.lower() != ".pptx":
                        raise ValueError(f"PPT template not found or not a .pptx file: {ppt_tpl}")
                    raw["presentation_template"] = ppt_tpl
                else:
                    raw.pop("presentation_template", None)
                path = save_project_settings(config.root, raw)
                return json_response(self, {"saved": str(path), "managed": path.name != "video-project.json", "message": "Configuration saved in the application workspace." if path.name != "video-project.json" else "Configuration saved in the product project."})
            return json_response(self, {"error": "not found"}, 404)
        except Exception as error:  # noqa: BLE001 - GUI must report request failures as JSON.
            if client_disconnected(error):
                return
            json_response(self, {"error": str(error)}, 400)



def websocket_thread(host: str, port: int) -> None:
    from websockets.sync.server import serve

    def handler(connection) -> None:
        WS_CLIENTS.add(connection)
        try:
            connection.send(json.dumps({"type": "connected"}))
            connection.recv()
        except Exception:  # noqa: BLE001 - websocket clients may disconnect at any time.
            return
        finally:
            WS_CLIENTS.discard(connection)

    with serve(handler, host, port):
        threading.Event().wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local AI video generation web GUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8875)
    parser.add_argument("--websocket-port", type=int, default=8876)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    global HTTP_SERVER, SERVICE_INFO
    SERVICE_INFO = {"host": args.host, "port": args.port, "websocket_port": args.websocket_port, "debug": args.debug, "started_at": datetime.now(timezone.utc).isoformat()}
    threading.Thread(target=websocket_thread, args=(args.host, args.websocket_port), daemon=True).start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    HTTP_SERVER = server
    print(f"AI Video GUI: http://{args.host}:{args.port}/")
    print(f"WebSocket progress: ws://{args.host}:{args.websocket_port}/")
    server.serve_forever()
    server.server_close()
    HTTP_SERVER = None


if __name__ == "__main__":
    main()
