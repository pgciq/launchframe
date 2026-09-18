from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


class VideoApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LaunchFrame")
        self.geometry("980x700")
        self.project = tk.StringVar()
        self.primary_language = tk.StringVar(value="en-US")
        self.secondary_language = tk.StringVar(value="zh-CN")
        self.primary_voice = tk.StringVar(value="en-US-JennyNeural")
        self.secondary_voice = tk.StringVar(value="zh-CN-YunyangNeural")
        self.duration = tk.StringVar(value="")
        self.output = tk.Text(self, height=20, wrap="word")
        self.events: queue.Queue[str] = queue.Queue()
        self._build_ui()
        self.after(250, self._drain_output)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        config = ttk.LabelFrame(root, text="Project configuration", padding=10)
        config.pack(fill="x")
        self._row(config, 0, "Product project", self.project, self._browse)
        self._row(config, 1, "Primary language", self.primary_language)
        self._row(config, 2, "Secondary language", self.secondary_language)
        self._row(config, 3, "Primary voice", self.primary_voice)
        self._row(config, 4, "Secondary voice", self.secondary_voice)
        self._row(config, 5, "Target duration (seconds)", self.duration)

        actions = ttk.Frame(root, padding=(0, 10))
        actions.pack(fill="x")
        buttons = [
            ("Save configuration", self._save_config),
            ("Scan resources", lambda: self._run("scan")),
            ("Inspect project", lambda: self._run("inspect")),
            ("Build video", self._build),
            ("Show status", lambda: self._run("status")),
            ("Start Pi / CodeMie", self._start_pi),
        ]
        for label, command in buttons:
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 6))

        ttk.Label(root, text="Progress and command output").pack(anchor="w")
        self.output.pack(fill="both", expand=True)

    def _row(self, parent: ttk.Widget, row: int, label: str, variable: tk.StringVar, command=None) -> None:
        ttk.Label(parent, text=label, width=24).grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, textvariable=variable, width=80)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        if command:
            ttk.Button(parent, text="Browse", command=command).grid(row=row, column=2, padx=6)
        parent.columnconfigure(1, weight=1)

    def _browse(self) -> None:
        selected = filedialog.askdirectory(title="Select product video project")
        if selected:
            self.project.set(selected)

    def _config_path(self) -> Path:
        project = Path(self.project.get()).expanduser().resolve()
        return project / "video-project.json"

    def _save_config(self) -> None:
        try:
            path = self._config_path()
            data = json.loads(path.read_text(encoding="utf-8"))
            data["primary_language"] = self.primary_language.get().strip() or "en-US"
            data["secondary_language"] = self.secondary_language.get().strip() or "zh-CN"
            data.setdefault("voices", {})["primary"] = self.primary_voice.get().strip()
            data.setdefault("voices", {})["secondary"] = self.secondary_voice.get().strip()
            if self.duration.get().strip():
                data.setdefault("output", {})["target_duration_seconds"] = float(self.duration.get())
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._log(f"Saved configuration: {path}")
        except Exception as error:  # noqa: BLE001 - GUI must surface any operation failure
            messagebox.showerror("Configuration error", str(error))

    def _run(self, command: str, extra: list[str] | None = None) -> None:
        if not self.project.get().strip():
            messagebox.showwarning("Project required", "Select a product project directory first.")
            return
        self._start_process([command, self.project.get(), *(extra or [])])

    def _build(self) -> None:
        if not self.project.get().strip():
            messagebox.showwarning("Project required", "Select a product project directory first.")
            return
        self._start_process(["build", self.project.get()])

    def _start_process(self, arguments: list[str]) -> None:
        cli = Path(sys.executable).with_name("launchframe.exe" if os.name == "nt" else "launchframe")
        if not cli.exists():
            cli = Path(sys.executable)
            arguments = ["-m", "cli", *arguments]
        self._log("$ " + " ".join([str(cli), *arguments]))
        threading.Thread(target=self._worker, args=(str(cli), arguments), daemon=True).start()

    def _worker(self, executable: str, arguments: list[str]) -> None:
        try:
            process = subprocess.Popen([executable, *arguments], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            assert process.stdout is not None
            for line in process.stdout:
                self.events.put(line.rstrip())
            code = process.wait()
            self.events.put(f"Process finished with exit code {code}")
        except Exception as error:  # noqa: BLE001 - GUI must surface any operation failure
            self.events.put(f"Process error: {error}")

    def _start_pi(self) -> None:
        try:
            subprocess.Popen(["pi"], cwd=self.project.get() or None)
            self._log("Started Pi. Use /login codemie and /model to select the enterprise model.")
        except Exception as error:  # noqa: BLE001 - GUI must surface any operation failure
            messagebox.showerror("Pi start failed", str(error))

    def _log(self, message: str) -> None:
        self.events.put(message)

    def _drain_output(self) -> None:
        while not self.events.empty():
            self.output.insert("end", self.events.get() + "\n")
            self.output.see("end")
        self.after(250, self._drain_output)


def main() -> None:
    VideoApp().mainloop()


if __name__ == "__main__":
    main()
