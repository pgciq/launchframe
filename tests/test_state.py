from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from video_mcp.state import WorkflowState, read_state


class WorkflowStateTests(unittest.TestCase):
    def test_initial_state_is_written_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = WorkflowState(root)
            self.assertTrue(state.path.exists())
            on_disk = json.loads(state.path.read_text(encoding="utf-8"))
            self.assertEqual(on_disk["status"], "created")
            self.assertEqual(on_disk["stage"], "created")
            self.assertEqual(on_disk["events"], [])

    def test_update_appends_a_new_event_for_a_new_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = WorkflowState(Path(directory))
            state.update("narration", status="running")
            self.assertEqual(state.data["stage"], "narration")
            self.assertEqual(state.data["status"], "running")
            self.assertEqual(len(state.data["events"]), 1)
            self.assertEqual(state.data["events"][0]["stage"], "narration")

    def test_update_completes_the_previous_running_event_on_stage_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = WorkflowState(Path(directory))
            state.update("narration", status="running")
            state.update("subtitles", status="running")
            self.assertEqual(state.data["events"][0]["status"], "completed")
            self.assertEqual(state.data["events"][1]["status"], "running")
            self.assertEqual(len(state.data["events"]), 2)

    def test_update_merges_into_the_same_event_when_stage_repeats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = WorkflowState(Path(directory))
            state.update("render", status="running", progress=10)
            state.update("render", status="running", progress=50)
            self.assertEqual(len(state.data["events"]), 1)
            self.assertEqual(state.data["events"][0]["progress"], 50)

    def test_update_extra_details_are_recorded_on_the_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = WorkflowState(Path(directory))
            state.update("render", status="failed", error="ffmpeg missing")
            self.assertEqual(state.data["events"][-1]["error"], "ffmpeg missing")


class ReadStateTests(unittest.TestCase):
    def test_returns_none_when_no_state_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertIsNone(read_state(Path(directory)))

    def test_returns_the_persisted_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            WorkflowState(root)
            data = read_state(root)
            self.assertIsNotNone(data)
            self.assertEqual(data["status"], "created")

    def test_reconciles_stale_running_events_from_an_old_stage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = WorkflowState(root)
            state.update("narration", status="running")
            # Simulate a crash: manually force the current stage forward
            # without going through update(), leaving a stale "running" event.
            state.data["stage"] = "subtitles"
            state.write()
            data = read_state(root)
            self.assertEqual(data["events"][0]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
