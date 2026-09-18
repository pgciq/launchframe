# Troubleshooting

## Scripts are blocked

Unblock the downloaded ZIP before extracting, or run:

```text
unblock-scripts.bat
```

`RemoteSigned` is usually handled by unblocking. If PowerShell reports **"running scripts is disabled on this system"**, run setup with a process-scoped bypass:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -InstallMissing
```

Check policy scope with `Get-ExecutionPolicy -List`. If `MachinePolicy` or `UserPolicy` is enforced, contact IT Security; do not change the company-wide policy without approval. `AllSigned`, AppLocker, and WDAC require company signing or IT approval.

## Ports are occupied

```powershell
.\stop.ps1
.\run.ps1
```

`run.ps1` automatically selects another localhost port pair when 8875/8876 are occupied.

## FFmpeg is missing

Install FFmpeg through Winget:

```powershell
winget install Gyan.FFmpeg.Shared
```

The manual fallback remains available when Winget is unavailable:

```powershell
.\tools\install-ffmpeg.ps1
```

The fallback script downloads a public FFmpeg build and verifies its SHA256 checksum.

## Resource folder selection

The selected product resource directory becomes the access boundary for the current run. It does not need `video-project.json`; the application scans supported resources and keeps settings internally. If the selected folder is empty, add a supported document, image, table, PDF/DOCX, or presentation before starting the build.

## Provider model list is empty

Check authentication, DIAL VPN access, Token validity, and the Activity log. Restart the Web GUI after installing Pi packages.

## Stale workflow state

Click `Refresh status`. If output files exist, the GUI reconciles stale running/failed state entries from older processes.

## Cancel a running build

Click the active (pulsing) build button a second time. A confirmation dialog appears:

- **Continue** — dismiss the dialog and keep the build running.
- **Terminate** — cancel the current build. Pi operations stop immediately; backend jobs write `cancelled` to `run-state.json`.

## Pi status shows "Pi starting…" for a long time

Pi starts automatically when a product resource directory is loaded. If it stays at "Pi starting...":

1. Check the **Activity log** for a specific error message.
2. Verify Pi is installed: `pi --version` in PowerShell.
3. Reload the directory using **Load selected folder** — this resets the Pi state and retries startup.
4. If CodeMie SSO is expired, click **Login CodeMie SSO** to reauthenticate; the stored session is reused across service restarts when its access or refresh credential is available.

## CodeMie SSO repeatedly opens the login page

A valid CodeMie session is stored for the current Windows user and reused after service restarts. If the browser reports success but the GUI still waits for authentication:

1. Close the current browser login tab.
2. Use the floating **Service** button → **Exit application** to stop the backend.
3. Restart the desktop shortcut and click **Login CodeMie SSO** once.
4. If it still fails, check that the same Windows user is running the GUI and that `%USERPROFILE%\\.pi\\agent\\auth.json` is readable.

The GUI prevents concurrent login requests and recognizes both shared CodeMie Web and CodeMie CLI SSO credentials.

## Activity log scrolling

The log auto-scrolls to the latest entry during a build. Click **Pause log** to stop auto-scrolling and inspect earlier entries. Click **Resume log** to return to live scrolling.
