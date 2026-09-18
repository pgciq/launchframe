from __future__ import annotations

import html
from pathlib import Path

import markdown

ROOT = Path(__file__).parents[1]
PUBLIC = ROOT / "public"

DOCUMENTS = [
    ("README", ROOT / "README.md"),
    ("Documentation home", ROOT / "docs" / "index.md"),
    ("Quick start", ROOT / "docs" / "quick-start.md"),
    ("User workflow", ROOT / "docs" / "user-workflow.md"),
    ("Providers and models", ROOT / "docs" / "providers.md"),
    ("Troubleshooting", ROOT / "docs" / "troubleshooting.md"),
    ("Promotion and demo video", ROOT / "docs" / "promotion.md"),
    ("First release (English)", ROOT / "docs" / "FIRST_RELEASE.md"),
    ("第一版流程（中文）", ROOT / "docs" / "FIRST_RELEASE.zh-CN.md"),
    ("Resource layout", ROOT / "docs" / "RESOURCE_LAYOUT.md"),
    ("Architecture workflow", ROOT / "VIDEO_GENERATION_WORKFLOW.md"),
    ("架构流程（中文）", ROOT / "VIDEO_GENERATION_WORKFLOW.zh-CN.md"),
]

STYLE = """
body { font-family: system-ui, sans-serif; max-width: 1100px; margin: 0 auto; padding: 24px; color: #172840; }
nav { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 24px; padding: 12px; background: #eef4fb; border-radius: 8px; }
nav a { color: #075ea8; text-decoration: none; }
pre { overflow-x: auto; padding: 12px; background: #f4f7fb; border-radius: 6px; }
code { background: #eef4fb; padding: 2px 4px; border-radius: 3px; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #cbd5e1; padding: 8px; text-align: left; }
th { background: #eef4fb; }
"""


def page(title: str, body: str) -> str:
    links = " ".join(f'<a href="{name}.html">{html.escape(label)}</a>' for name, label, _ in PAGES)
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{STYLE}</style></head><body><nav><a href='index.html'>Home</a>{links}</nav>{body}</body></html>"


PAGES = [(Path(path).stem, label, path) for label, path in DOCUMENTS]
PUBLIC.mkdir(parents=True, exist_ok=True)
for name, label, source in PAGES:
    text = source.read_text(encoding="utf-8")
    body = markdown.markdown(text, extensions=["fenced_code", "tables"])
    (PUBLIC / f"{name}.html").write_text(page(label, body), encoding="utf-8")

index_body = "<h1>LaunchFrame</h1><p>Review-gated local product promotional video workflow.</p><ul>" + "".join(f'<li><a href="{name}.html">{html.escape(label)}</a></li>' for name, label, _ in PAGES) + "</ul>"
(PUBLIC / "index.html").write_text(page("LaunchFrame", index_body), encoding="utf-8")
