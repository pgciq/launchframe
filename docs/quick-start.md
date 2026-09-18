# Quick start

## First Windows installation

Extract the Source ZIP or clone the repository, then double-click:

```text
install.bat
```

`install.bat` is the normal one-step installer. It:

- unblocks the downloaded PowerShell and batch scripts;
- installs missing Python and FFmpeg;
- creates the virtual environment and installs project dependencies;
- creates or updates the desktop shortcut;
- asks whether to start the Web GUI.

No separate `unblock-scripts.bat`, `setup.ps1`, or `run.ps1` command is required for a normal first installation. The normal shortcut hides the backend console; use `debug.bat` when visible backend output is needed.

After accepting the start prompt, select a folder containing product resources in the Web GUI. It becomes the access boundary for the run. A `video-project.json` file is not required.

## If no Azure Speech resource exists

If no Speech resource is available, sign in to the Azure Portal and ask an Azure administrator or authorized user to create or select an Azure AI Speech resource. Then return to the GUI and click `Refresh Speech resources`.

Creating Azure resources is intentionally outside LaunchFrame. The project does not create subscriptions, resource groups, Speech resources, or Speech keys. Without Speech, Vision, Draft, PPT, and PDF review remain available; audio, subtitles, and video require a configured Speech resource.

## First workflow

| Step | Action | What happens |
|------|--------|--------------|
| 1 | Select product resource folder | Access boundary set; auto-scan; Pi starts |
| 2 | Azure login | Subscription → Speech resource → Voice catalog |
| 3 | Provider login + model | CodeMie SSO / DIAL token / ELITEA token; save config |
| 4 | **Vision** _(optional)_ | Pi Vision LLM analyzes images → review → **Approve Vision** |
| 5 | **Draft** | Customize/load/save the Draft prompt → Pi LLM generates outline + EN/ZH narration → edit → **Approve Draft** |
| 6 | **Build PPT** | Customize/load/save the PPT prompt → python-pptx → PPTX; PowerPoint COM/macOS PowerPoint automation/LibreOffice → PDF → review |
| 7 | **Build audio + subtitles** | Azure Neural TTS per slide → merged WAV; word boundaries → SRT/VTT → automatically accepted after generation |
| 8 | **Build video** | FFmpeg: slides + WAV + VTT → primary / secondary / dual-track MP4 |
| 9 | Review & deliver | Play videos locally → download → upload manually |

Use `Progress details` to inspect the backend PID, HTTP/WebSocket ports, Pi state, active jobs, and recent backend logs. Use the red `Exit` button to stop the application safely. The browser tab may need to be closed manually after the backend stops.

To remove the local installation safely, use `uninstall.bat`. It stops the backend, removes installer-created local files and the desktop shortcut, and preserves product data and shared tools. Use `-RemoveInstallationDirectory` only with the explicit `DELETE` confirmation.

To cancel a running build, click the active (pulsing yellow) button a second time and confirm in the dialog.
