from __future__ import annotations

import asyncio
import http.client
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DEFAULT_REPOSITORY = ""


def az_command() -> str:
    command = shutil.which("az.cmd") or shutil.which("az")
    if not command:
        raise RuntimeError("Azure CLI is not available in PATH")
    return command


@dataclass(frozen=True)
class SpeechResource:
    id: str
    name: str
    resource_group: str
    location: str
    endpoint: str


def ensure_checkout(config: Any) -> Path:
    checkout = (config.root / config.azure.checkout_dir).resolve()
    project_vendor = Path(__file__).parents[1] / "vendor" / "azure-mcp"
    if (project_vendor / "server.py").exists():
        azure_root = project_vendor
    else:
        checkout.parent.mkdir(parents=True, exist_ok=True)
        bundled_server = checkout / "server.py"
        cloned_server = checkout / "azure-mcp" / "server.py"
        if bundled_server.exists():
            azure_root = checkout
        else:
            if not config.azure.repository:
                raise RuntimeError("Bundled azure-mcp is unavailable; configure azure.repository with a permitted repository URL.")
            if not cloned_server.exists():
                command = ["git", "clone", "--depth", "1", "--branch", config.azure.ref, config.azure.repository, str(checkout)]
                subprocess.run(command, check=True)
            azure_root = checkout / "azure-mcp"
    if not (azure_root / "server.py").exists():
        raise RuntimeError(f"azure-mcp server was not found: {azure_root / 'server.py'}")
    marker = azure_root / ".video-mcp-installed"
    marker_value = marker.read_text(encoding="utf-8") if marker.exists() else ""
    if f"python={sys.executable}\n" not in marker_value:
        subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(azure_root)], check=True)
        marker.write_text(f"python={sys.executable}\n", encoding="utf-8")
    return azure_root


def _call(config: Any, tool: str, arguments: dict[str, Any] | None = None) -> Any:
    checkout = ensure_checkout(config)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[str(checkout / "server.py")],
        cwd=str(checkout),
        env=os.environ.copy(),
    )

    async def run() -> Any:
        async with stdio_client(parameters) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments or {})
            texts = [item.text for item in result.content if getattr(item, "type", None) == "text"]
            return json.loads("\n".join(texts)) if texts else result

    return asyncio.run(run())


def login() -> dict[str, Any]:
    try:
        current = subprocess.run([az_command(), "account", "show", "-o", "json"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        from azure.identity import InteractiveBrowserCredential
        credential = InteractiveBrowserCredential()
        credential.get_token("https://management.azure.com/.default")
        return {"status": "authenticated", "method": "interactive_browser_credential"}
    if current.returncode == 0 and current.stdout.strip():
        return {"status": "already_authenticated", "account": json.loads(current.stdout)}
    subprocess.Popen([az_command(), "login"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"status": "login_started", "message": "Azure login was started. Complete the browser authentication, then check status again."}


def logout() -> dict[str, Any]:
    try:
        result = subprocess.run([az_command(), "logout"], capture_output=True, text=True, check=False)
    except RuntimeError:
        return {"status": "logout_unavailable", "message": "No Azure CLI session was found. Clear the Azure identity cache if needed."}
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Azure logout failed")
    return {"status": "logged_out"}


def login_status() -> dict[str, Any]:
    try:
        result = subprocess.run([az_command(), "account", "show", "-o", "json"], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return {"status": "not_authenticated", "method": "interactive_browser_credential", "message": "Click Login Azure to open the browser authentication flow."}
    if result.returncode != 0:
        return {"status": "not_authenticated", "method": "azure_cli", "message": "Click Login Azure or run az login."}
    return {"status": "authenticated", "account": json.loads(result.stdout)}


def account(config: Any) -> list[dict[str, str]]:
    """Return Azure subscriptions in the stable shape consumed by the GUI.

    The Web GUI authenticates through Azure CLI on Windows. Prefer the same
    CLI session for subscription discovery instead of making the first request
    through ``DefaultAzureCredential``. The latter probes managed identity
    endpoints before reaching the CLI credential and can block for a long time
    on a normal desktop or corporate network.
    """
    try:
        command = az_command()
    except RuntimeError:
        raw = _call(config, "azure_auth_status")
    else:
        result = subprocess.run(
            [command, "account", "list", "--output", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or "Azure CLI could not list subscriptions."
            raise RuntimeError(f"Azure subscription discovery failed: {message} Run az login and retry.")
        try:
            raw = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as error:
            raise RuntimeError("Azure CLI returned invalid subscription data.") from error
    if isinstance(raw, dict):
        for key in ("subscriptions", "scopes", "items", "data"):
            candidate = raw.get(key)
            if isinstance(candidate, list):
                raw = candidate
                break
        else:
            raw = [raw] if raw else []
    if not isinstance(raw, list):
        return []
    subscriptions: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        subscription_id = str(item.get("subscription_id") or item.get("scope_id") or item.get("id") or "").strip()
        if not subscription_id:
            continue
        subscriptions.append({
            "subscription_id": subscription_id,
            "display_name": str(item.get("display_name") or item.get("name") or subscription_id),
            "state": str(item.get("state") or "Enabled"),
        })
    return subscriptions


def _cli_resources(subscription_id: str) -> list[dict[str, Any]] | None:
    """List resources through the same Azure CLI session used by the GUI login."""
    try:
        command = az_command()
    except RuntimeError:
        return None
    try:
        result = subprocess.run(
            [command, "resource", "list", "--subscription", subscription_id, "--output", "json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Azure resource discovery timed out. Check the Azure CLI session and network connection.") from error
    if result.returncode != 0:
        message = result.stderr.strip() or "Azure CLI could not list resources."
        raise RuntimeError(f"Azure resource discovery failed: {message} Run az login and retry.")
    try:
        raw = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as error:
        raise RuntimeError("Azure CLI returned invalid resource data.") from error
    return raw if isinstance(raw, list) else []


def speech_resources(config: Any, subscription_id: str | None = None) -> list[SpeechResource]:
    selected_subscription = subscription_id or config.azure.subscription_id
    if not selected_subscription:
        scopes = _call(config, "azure_auth_status") or []
        if not scopes:
            raise RuntimeError("No accessible Azure subscriptions were found")
        selected_subscription = scopes[0].get("subscription_id")
    rows = _cli_resources(selected_subscription)
    if rows is None:
        rows = _call(config, "list_resources", {"subscription_id": selected_subscription}) or []
    return [
        SpeechResource(
            id=str(item["id"]),
            name=str(item["name"]),
            resource_group=str(item.get("resource_group") or item.get("resourceGroup") or ""),
            location=str(item.get("location") or ""),
            endpoint=str(item.get("endpoint") or ""),
        )
        for item in rows
        if str(item.get("type", "")).lower() == "microsoft.cognitiveservices/accounts"
    ]


def _arm_token() -> str:
    from azure.identity import DefaultAzureCredential
    credential = DefaultAzureCredential(
        exclude_interactive_browser_credential=False,
        exclude_managed_identity_credential=True,
    )
    return credential.get_token("https://management.azure.com/.default").token


def speech_key(resource: SpeechResource) -> str:
    url = f"https://management.azure.com{resource.id}/listKeys?api-version=2023-05-01"
    request = urllib.request.Request(
        url,
        data=b"{}",
        headers={"Authorization": f"Bearer {_arm_token()}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            key = json.loads(response.read().decode("utf-8")).get("key1", "")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Speech key retrieval failed: {error.code}") from error
    if not key:
        raise RuntimeError(f"No Speech key returned for resource {resource.name}")
    return str(key)


def tts_voices(resource: SpeechResource, key: str) -> list[dict[str, Any]]:
    url = f"https://{resource.location}.tts.speech.microsoft.com/cognitiveservices/voices/list"
    request = urllib.request.Request(url, headers={"Ocp-Apim-Subscription-Key": key})
    last_error: Exception | None = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except http.client.IncompleteRead as error:
            last_error = error
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Azure Speech voices request failed: {error.code}") from error
    raise RuntimeError("Azure Speech voice catalog response was incomplete after 3 attempts") from last_error


def resolve_speech(config: Any) -> tuple[SpeechResource, str, list[dict[str, Any]]]:
    account(config)
    resources = speech_resources(config, config.azure.subscription_id)
    resource_id = config.azure.speech_resource_id
    if resource_id:
        selected = next((item for item in resources if item.id == resource_id), None)
    elif len(resources) == 1:
        selected = resources[0]
    else:
        selected = None
    if selected is None:
        names = ", ".join(item.name for item in resources) or "none"
        raise RuntimeError(f"Select azure.speech_resource_id. Accessible Speech resources: {names}")
    key = speech_key(selected)
    return selected, key, tts_voices(selected, key)
