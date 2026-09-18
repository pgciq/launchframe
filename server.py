"""MCP server for resource-driven narrated video generation."""

from __future__ import annotations

import json
from dataclasses import replace

from mcp.server.fastmcp import FastMCP

from video_mcp.azure_mcp import login_status, resolve_speech, speech_resources
from video_mcp.config import load_project, project_path
from video_mcp.llm import generate_content_draft
from video_mcp.pipeline import build_project, inspect_project
from video_mcp.resources import IGNORED_RESOURCE_DIRECTORIES, scan
from video_mcp.vision import analyze_images

mcp = FastMCP("launchframe")


@mcp.tool()
def azure_login_status(project_dir: str) -> str:
    """Check the active Azure identity used by the selected azure-mcp checkout."""
    return json.dumps(login_status(), ensure_ascii=False, indent=2)


@mcp.tool()
def discover_speech_resources(project_dir: str, subscription_id: str | None = None) -> str:
    """List accessible Azure Speech resources through the configured azure-mcp checkout."""
    config = load_project(project_dir)
    resources = speech_resources(config, subscription_id)
    return json.dumps([resource.__dict__ for resource in resources], ensure_ascii=False, indent=2)


@mcp.tool()
def list_tts_voices(project_dir: str, resource_id: str, subscription_id: str | None = None) -> str:
    """Return supported TTS voices for a selected Azure Speech resource."""
    config = load_project(project_dir)
    azure_config = replace(config.azure, speech_resource_id=resource_id, subscription_id=subscription_id or config.azure.subscription_id)
    resource, key, voices = resolve_speech(replace(config, azure=azure_config))
    # The key is used only for the request and is never returned.
    del key
    return json.dumps({"resource": resource.__dict__, "voices": voices}, ensure_ascii=False, indent=2)


@mcp.tool()
def scan_product_resources(project_dir: str) -> str:
    """Categorize product files by presentation, content, image, table, video, and audio type."""
    root = project_path(project_dir)
    return json.dumps({"project_dir": str(root), "resources": scan(root)}, ensure_ascii=False, indent=2)


@mcp.tool()
def inspect_video_project(project_dir: str) -> str:
    """Validate a product video project directory and return its resource manifest."""
    return json.dumps(inspect_project(load_project(project_dir)), ensure_ascii=False, indent=2)


@mcp.tool()
def analyze_product_images(project_dir: str) -> str:
    """Analyze product images with an optional Vision LLM and write a reviewable report."""
    config = load_project(project_dir)
    if not config.vision.enabled:
        raise ValueError("vision_analysis.enabled is false")
    results = analyze_images(config, config.root / ".video-work")
    return json.dumps({"report": str(config.root / ".video-work" / "vision-analysis.json"), "images": len(results)}, ensure_ascii=False, indent=2)


@mcp.tool()
def generate_content_draft_tool(project_dir: str) -> str:
    """Extract product materials with the optional LLM stage and write a reviewable draft."""
    config = load_project(project_dir)
    work = config.root / ".video-work"
    draft = generate_content_draft(config, work)
    return json.dumps({"draft": str(work / "content-draft.json"), "slides": len(draft.get("outline", []))}, indent=2)


@mcp.tool()
def build_video_project(project_dir: str) -> str:
    """Generate narration, subtitles, PDF, and English/Mandarin videos for a product project."""
    return json.dumps(build_project(load_project(project_dir)), ensure_ascii=False, indent=2)


@mcp.tool()
def list_product_resources(project_dir: str) -> str:
    """List files under a validated product project without reading their contents."""
    root = project_path(project_dir)
    files = [
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and not any(part in IGNORED_RESOURCE_DIRECTORIES for part in path.parts)
    ]
    return json.dumps({"project_dir": str(root), "files": sorted(files)}, ensure_ascii=False, indent=2)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
