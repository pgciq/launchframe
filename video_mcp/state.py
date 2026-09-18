from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WorkflowState:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / ".video-work" / "run-state.json"
        self.data: dict[str, Any] = {
            "run_id": str(uuid.uuid4()),
            "status": "created",
            "stage": "created",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "events": [],
        }
        self.write()

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def update(self, stage: str, status: str = "running", **details: Any) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        self.data.update({"stage": stage, "status": status, "updated_at": updated_at})
        events = self.data["events"]
        if events and events[-1].get("stage") == stage:
            events[-1].update({"status": status, "at": updated_at, **details})
        else:
            if events and events[-1].get("status") == "running":
                events[-1]["status"] = "completed"
            events.append({"stage": stage, "status": status, "at": updated_at, **details})
        self.write()


def read_state(project_dir: Path) -> dict[str, Any] | None:
    path = project_dir / ".video-work" / "run-state.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    current_stage = data.get("stage")
    changed = False
    for event in data.get("events", []):
        if event.get("status") == "running" and event.get("stage") != current_stage:
            event["status"] = "completed"
            changed = True
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data
