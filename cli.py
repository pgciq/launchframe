from __future__ import annotations

import argparse
import json

from video_mcp.config import load_project
from video_mcp.pipeline import build_project, inspect_project
from video_mcp.resources import scan
from video_mcp.state import read_state


def main() -> None:
    parser = argparse.ArgumentParser(description="LaunchFrame local promotional video pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "inspect", "build", "status"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("project_dir")
    args = parser.parse_args()
    config = load_project(args.project_dir)
    if args.command == "scan":
        result = {"project_dir": str(config.root), "resources": scan(config.root)}
    elif args.command == "status":
        result = read_state(config.root) or {"status": "not_started"}
    elif args.command == "inspect":
        result = inspect_project(config)
    elif args.command == "build":
        result = build_project(config)
    else:
        result = build_project(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
