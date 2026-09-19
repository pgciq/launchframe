#!/usr/bin/env bash
# Cross-platform bootstrap for LaunchFrame.
# macOS: uses Homebrew for dependency installation.
# Linux: uses apt-get for dependency installation.
set -Eeuo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
INSTALL_MISSING=0
PROJECT_ROOT=""

usage() {
  cat <<'EOF'
Usage: ./setup.sh [--install-missing] [--project-root PATH]

  --install-missing   Install missing system packages, including Python 3.10+,
                      without prompting, using Homebrew or apt-get.
  --project-root PATH Persist VIDEO_PROJECT_ROOT in the generated .install-manifest.json
                      and export it for this setup process.

When --install-missing is not supplied and missing software is detected,
setup.sh asks a single yes/no question before installing anything
(default: yes).
EOF
}

while (($#)); do
  case "$1" in
    --install-missing) INSTALL_MISSING=1; shift ;;
    --project-root)
      [[ $# -ge 2 ]] || { echo "--project-root requires a path" >&2; exit 2; }
      PROJECT_ROOT="$(CDPATH= cd -- "$2" && pwd)"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

OS="$(uname -s)"
case "$OS" in
  Darwin) PLATFORM="macos" ;;
  Linux) PLATFORM="linux" ;;
  *) echo "Unsupported platform: $OS" >&2; exit 1 ;;
esac

# Homebrew's auto-update step downloads its own metadata/tooling before every
# `brew install`, which can silently stall for a very long time on a slow or
# restricted network (observed to hang 10+ minutes with no visible progress,
# making the script look like it "did not install" anything). Skip it here;
# formulae are still installed normally, just without refreshing the tap
# first. Run `brew update` manually if you need the latest formula versions.
export HOMEBREW_NO_AUTO_UPDATE=1

have() { command -v "$1" >/dev/null 2>&1; }
have_macos_powerpoint() {
  [[ "$PLATFORM" == "macos" ]] || return 1
  [[ -d "/Applications/Microsoft PowerPoint.app" || -d "$HOME/Applications/Microsoft PowerPoint.app" ]] && return 0
  have mdfind && mdfind "kMDItemCFBundleIdentifier == 'com.microsoft.Powerpoint'" 2>/dev/null | grep -q 'Microsoft PowerPoint.app'
}
run_root() {
  if [[ "$(id -u)" -eq 0 ]]; then "$@"; else sudo "$@"; fi
}

# Ask a single yes/no question, defaulting to yes when the user just presses
# Enter. Mirrors setup.ps1's confirmation prompt, but defaults to yes here.
# Returns 0 (yes) immediately when --install-missing was already supplied, or
# when running non-interactively (no TTY, or $CI is set) with no explicit
# flag, in which case it defaults to "no" so unattended runs never block.
confirm_install() {
  local prompt="$1"
  if [[ "$INSTALL_MISSING" -eq 1 ]]; then return 0; fi
  if [[ -n "${CI:-}" ]] || [[ ! -t 0 ]]; then
    echo "$prompt [non-interactive, skipping automatic installation]" >&2
    return 1
  fi
  local reply
  # Read directly from the controlling terminal when possible so the prompt
  # still works if stdout is also being piped to tee or a log file. Fall
  # back to plain stdin when /dev/tty is not available (e.g. some sandboxed
  # or pty-less environments).
  printf '%s [Y/n] ' "$prompt"
  if ! read -r reply < /dev/tty 2>/dev/null; then
    read -r reply || reply=""
  fi
  reply="${reply:-Y}"
  [[ "$reply" =~ ^[Yy] ]]
}

install_packages() {
  echo "[INFO] Installing: $* (this can take a few minutes; downloads run in the foreground with no separate spinner)..."
  if [[ "$PLATFORM" == "macos" ]]; then
    have brew || { echo "Homebrew is required to install missing software: https://brew.sh" >&2; return 1; }
    # -y/--yes skips Homebrew's own "Do you want to proceed with the
    # installation?" confirmation, which it now shows before installs that
    # pull in many dependencies (for example on Intel Macs, which no longer
    # get prebuilt bottles and must build several formulae from source).
    # Without this flag the command blocks forever waiting for input that
    # setup.sh never sends.
    brew install -y "$@"
  else
    have apt-get || { echo "apt-get is required to install missing software on Linux." >&2; return 1; }
    run_root apt-get update
    run_root apt-get install -y "$@"
  fi
  echo "[OK] Finished installing: $*"
}

# Azure CLI's Homebrew formula depends on python@3.14, and one of its
# transitive Python dependencies (cryptography) has no prebuilt wheel for
# older Intel Macs on recent versions. That forces Homebrew to bootstrap a
# full Rust + LLVM toolchain from source just to compile one package, which
# can take 30-90+ minutes. Installing azure-cli into its own venv with pip
# uses precompiled wheels instead and finishes in a couple of minutes.
install_azure_cli() {
  local venv_dir="$ROOT/.azure-cli-venv"
  echo "[INFO] Installing Azure CLI via pip (isolated venv) instead of Homebrew/apt to avoid a slow from-source Rust/LLVM build..."
  "$PYTHON" -m venv "$venv_dir"
  "$venv_dir/bin/python" -m pip install --upgrade pip >/dev/null

  local cryptography_pin=()
  if [[ "$PLATFORM" == "macos" ]] && [[ "$(uname -m)" == "x86_64" ]]; then
    # PyPI dropped macOS x86_64 wheels for cryptography>=49, which forces a
    # from-source build requiring Rust -- exactly what this function exists
    # to avoid. Pin to the last version that still ships an Intel wheel.
    cryptography_pin=("cryptography<49")
  fi
  "$venv_dir/bin/pip" install "${cryptography_pin[@]}" azure-cli

  local target_bin=""
  if [[ "$PLATFORM" == "macos" ]] && have brew; then
    local brew_bin="$(brew --prefix)/bin"
    [[ -w "$brew_bin" ]] && target_bin="$brew_bin"
  fi
  if [[ -z "$target_bin" ]]; then
    local candidate
    for candidate in /usr/local/bin "$HOME/.local/bin"; do
      [[ -d "$candidate" && -w "$candidate" ]] && { target_bin="$candidate"; break; }
    done
  fi
  if [[ -z "$target_bin" ]]; then
    target_bin="$HOME/.local/bin"
    mkdir -p "$target_bin"
  fi
  ln -sf "$venv_dir/bin/az" "$target_bin/az"
  echo "[OK] Azure CLI installed: $target_bin/az -> $venv_dir/bin/az"
  case ":$PATH:" in
    *":$target_bin:"*) ;;
    *) echo "[WARN] $target_bin is not on PATH. Add it, e.g.: export PATH=\"$target_bin:\$PATH\"" >&2 ;;
  esac
}

python_supported() {
  "$1" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
}

find_supported_python() {
  local candidate path
  for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
    path="$(command -v "$candidate" 2>/dev/null || true)"
    if [[ -n "$path" ]] && python_supported "$path"; then
      PYTHON="$path"
      return 0
    fi
  done

  # Versioned Homebrew formulae can be keg-only and therefore absent from PATH.
  if [[ "$PLATFORM" == "macos" ]] && have brew; then
    path="$(brew --prefix python@3.12 2>/dev/null || true)/bin/python3.12"
    if [[ -x "$path" ]] && python_supported "$path"; then
      PYTHON="$path"
      return 0
    fi
  fi
  return 1
}

install_python() {
  if [[ "$PLATFORM" == "macos" ]]; then
    have brew || {
      echo "Homebrew is required to install Python automatically: https://brew.sh" >&2
      return 1
    }
    brew install -y python@3.12
  else
    have apt-get || {
      echo "apt-get is required to install Python automatically on Linux." >&2
      return 1
    }

    local package="" venv_package
    for package in python3.12 python3.11 python3.10; do
      if apt-cache show "$package" >/dev/null 2>&1; then
        break
      fi
      package=""
    done
    [[ -n "$package" ]] || {
      echo "Could not find an apt package for Python 3.10+; install it manually and rerun setup.sh." >&2
      return 1
    }

    venv_package="${package}-venv"
    if ! apt-cache show "$venv_package" >/dev/null 2>&1; then
      venv_package="python3-venv"
    fi
    run_root apt-get update
    run_root apt-get install -y "$package" "$venv_package" python3-pip
  fi
}

# --- Detect everything that is missing before installing or prompting -----
declare -a MISSING_LABELS=()
PYTHON_MISSING=0
NODE_MISSING=0
GIT_MISSING=0
FFMPEG_MISSING=0
OFFICE_FALLBACK_MISSING=0
AZ_MISSING=0
PI_MISSING=0

if ! find_supported_python; then
  PYTHON_MISSING=1
  MISSING_LABELS+=("Python 3.10+")
fi
have node || { NODE_MISSING=1; MISSING_LABELS+=("Node.js"); }
have git || { GIT_MISSING=1; MISSING_LABELS+=("Git"); }
have ffmpeg || { FFMPEG_MISSING=1; MISSING_LABELS+=("FFmpeg"); }
# PowerPoint for Mac can export the PDF used by the native renderer. When it
# is absent, macOS and Linux use the LibreOffice + Poppler fallback path.
if have_macos_powerpoint; then
  echo "[INFO] Microsoft PowerPoint for Mac detected; LibreOffice/Poppler fallback is optional."
elif ! have soffice || ! have pdftoppm; then
  OFFICE_FALLBACK_MISSING=1
  MISSING_LABELS+=("LibreOffice/Poppler (PDF rendering fallback)")
fi
have az || { AZ_MISSING=1; MISSING_LABELS+=("Azure CLI"); }
have pi || { PI_MISSING=1; MISSING_LABELS+=("Pi CLI"); }

if ((${#MISSING_LABELS[@]} > 0)); then
  echo "Missing software detected: $(IFS=,; echo "${MISSING_LABELS[*]}" | sed 's/,/, /g')"
  if confirm_install "Install missing software automatically using Homebrew/apt-get?"; then
    INSTALL_MISSING=1
  else
    echo "Skipping automatic installation. Setup will continue and report what is still required." >&2
  fi
fi

# --- Python (bootstrap prerequisite; installed on its own before venv setup) ---
if [[ "$PYTHON_MISSING" -eq 1 ]]; then
  if [[ "$INSTALL_MISSING" -eq 1 ]]; then
    echo "[INFO] Python 3.10+ was not found. Installing it..."
    install_python
    find_supported_python || {
      echo "Python 3.10+ was installed but could not be found. Check your PATH and rerun setup.sh." >&2
      exit 1
    }
  else
    current_python="$(python3 --version 2>&1 || echo 'not installed')"
    echo "Python 3.10 or newer is required (found: $current_python)." >&2
    echo "Install it manually or rerun with: ./setup.sh --install-missing" >&2
    exit 1
  fi
fi
"$PYTHON" - <<'PY'
import sys
print(f"[OK] Python {sys.version.split()[0]}: {sys.executable}")
PY

# --- Remaining system packages ---------------------------------------------
if [[ "$INSTALL_MISSING" -eq 1 ]]; then
  declare -a PACKAGES=()
  if [[ "$PLATFORM" == "macos" ]]; then
    [[ "$NODE_MISSING" -eq 1 ]] && PACKAGES+=("node")
    [[ "$GIT_MISSING" -eq 1 ]] && PACKAGES+=("git")
    [[ "$FFMPEG_MISSING" -eq 1 ]] && PACKAGES+=("ffmpeg")
    [[ "$OFFICE_FALLBACK_MISSING" -eq 1 ]] && PACKAGES+=("libreoffice" "poppler")
  else
    [[ "$NODE_MISSING" -eq 1 ]] && PACKAGES+=("nodejs" "npm")
    [[ "$GIT_MISSING" -eq 1 ]] && PACKAGES+=("git")
    [[ "$FFMPEG_MISSING" -eq 1 ]] && PACKAGES+=("ffmpeg")
    [[ "$OFFICE_FALLBACK_MISSING" -eq 1 ]] && PACKAGES+=("libreoffice" "poppler-utils")
  fi
  if ((${#PACKAGES[@]} > 0)); then
    install_packages "${PACKAGES[@]}" || echo "[WARN] Some packages could not be installed automatically; see messages above." >&2
  fi
  # Azure CLI is installed separately via pip (see install_azure_cli), not
  # through Homebrew/apt, to avoid a slow from-source Rust/LLVM build.
  if [[ "$AZ_MISSING" -eq 1 ]]; then
    install_azure_cli || echo "[WARN] Azure CLI could not be installed automatically; see messages above." >&2
  fi
fi

for required in git node npm; do
  if have "$required"; then
    echo "[OK] $required: $(command -v "$required")"
  else
    echo "[WARN] $required was not found. Install it and rerun setup.sh." >&2
  fi
done
for optional in ffmpeg az; do
  if have "$optional"; then echo "[OK] $optional: $(command -v "$optional")"; else echo "[WARN] $optional was not found."; fi
done
if have_macos_powerpoint; then
  echo "[OK] Microsoft PowerPoint for Mac: native PDF renderer"
else
  for optional in soffice pdftoppm; do
    if have "$optional"; then echo "[OK] $optional: $(command -v "$optional")"; else echo "[WARN] $optional was not found."; fi
  done
fi

if [[ "$PI_MISSING" -eq 1 ]]; then
  if [[ "$INSTALL_MISSING" -eq 1 ]] && have npm; then
    echo "[INFO] Installing Pi CLI..."
    npm install --global @earendil-works/pi-coding-agent
  else
    echo "[INFO] Pi CLI was not found. Install it with: npm install --global @earendil-works/pi-coding-agent"
  fi
fi
if have pi; then echo "[OK] pi: $(command -v pi)"; fi

if ! have az; then
  if [[ "$PLATFORM" == "linux" ]]; then
    echo "[INFO] Azure CLI is not installed. Follow https://learn.microsoft.com/cli/azure/install-azure-cli-linux"
  else
    echo "[INFO] Azure CLI is not installed. Install it with: ./setup.sh --install-missing (uses pip, not Homebrew)"
  fi
fi

"$PYTHON" -m venv "$ROOT/.venv"
VENV_PYTHON="$ROOT/.venv/bin/python"
if ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
  "$VENV_PYTHON" -m ensurepip --upgrade
fi
if ! "$VENV_PYTHON" - <<'PY2'
import importlib.metadata
try: importlib.metadata.version("product-video-foundry")
except importlib.metadata.PackageNotFoundError: raise SystemExit(1)
PY2
then
  "$VENV_PYTHON" -m pip install -e "$ROOT"
else echo "[OK] product-video-foundry is already installed"
fi
if [[ -f "$ROOT/vendor/azure-mcp/pyproject.toml" ]]; then
  if ! "$VENV_PYTHON" - <<'PY2'
import importlib.metadata
try: importlib.metadata.version("azure-mcp")
except importlib.metadata.PackageNotFoundError: raise SystemExit(1)
PY2
  then "$VENV_PYTHON" -m pip install -e "$ROOT/vendor/azure-mcp"
  else echo "[OK] azure-mcp is already installed"
  fi
fi

if [[ -n "$PROJECT_ROOT" ]]; then
  export VIDEO_PROJECT_ROOT="$PROJECT_ROOT"
  echo "[OK] VIDEO_PROJECT_ROOT=$VIDEO_PROJECT_ROOT"
fi

VERSION="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$ROOT/pyproject.toml" | head -1)"
"$PYTHON" - "$ROOT" "$VERSION" "$PROJECT_ROOT" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
root = Path(sys.argv[1])
version = sys.argv[2]
project_root = sys.argv[3]
manifest = {
    "version": version,
    "installed_at": datetime.now(timezone.utc).isoformat(),
    "root": str(root),
    "created": [".venv"],
    "environment_variables": {"VIDEO_PROJECT_ROOT": project_root},
}
(root / ".install-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo
echo "Setup completed for $PLATFORM. Start the Web GUI with:"
echo "  ./run.sh"
if [[ -n "$PROJECT_ROOT" ]]; then
  echo "For future shells, export: export VIDEO_PROJECT_ROOT='$PROJECT_ROOT'"
fi
