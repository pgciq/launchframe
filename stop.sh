#!/usr/bin/env bash
# Stop the background Web GUI started by run.sh.
set -Eeuo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
RUNTIME_PATH="$ROOT/.video-work/web-gui-runtime.json"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -f "$RUNTIME_PATH" ]]; then
  echo "Product Video Foundry Web GUI is not running."
  exit 0
fi

if [[ -x "$PYTHON" ]]; then
  readarray -t runtime_info < <("$PYTHON" - "$RUNTIME_PATH" <<'PY'
import json, sys
try:
    data = json.loads(open(sys.argv[1], encoding="utf-8").read())
    print(data.get("pid", ""))
    print(data.get("port", ""))
    print(data.get("websocket_port", ""))
except Exception:
    print("\n\n")
PY
)
else
  runtime_info=()
fi

PID="${runtime_info[0]:-}"
PORT="${runtime_info[1]:-}"
WEBSOCKET_PORT="${runtime_info[2]:-}"

process_running() {
  [[ "$1" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$1" 2>/dev/null || return 1
  ps -p "$1" -o command= 2>/dev/null | grep -q '[w]eb_gui'
}

if process_running "$PID"; then
  echo "Stopping Product Video Foundry Web GUI process (PID $PID)..."
  kill "$PID" 2>/dev/null || true
  for _ in $(seq 1 20); do
    process_running "$PID" || break
    sleep 0.25
done
  if process_running "$PID"; then
    kill -KILL "$PID" 2>/dev/null || true
  fi
else
  if [[ -n "$PORT" || -n "$WEBSOCKET_PORT" ]]; then
    echo "Product Video Foundry Web GUI is not running on ports ${PORT:-?}, ${WEBSOCKET_PORT:-?}."
  else
    echo "Product Video Foundry Web GUI is not running."
  fi
fi

rm -f "$RUNTIME_PATH"
echo "Product Video Foundry Web GUI stopped."
