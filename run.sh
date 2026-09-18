#!/usr/bin/env bash
# Start the cross-platform Web GUI in the background.
set -Eeuo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
HOST="127.0.0.1"
PORT=8875
WEBSOCKET_PORT=8876
NO_BROWSER=0
DEBUG=0
REPLACE=0

usage() {
  cat <<'EOF'
Usage: ./run.sh [--host HOST] [--port PORT] [--websocket-port PORT]
               [--no-browser] [--debug] [--replace]
EOF
}
while (($#)); do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --websocket-port) WEBSOCKET_PORT="$2"; shift 2 ;;
    --no-browser) NO_BROWSER=1; shift ;;
    --debug) DEBUG=1; shift ;;
    --replace) REPLACE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]] || { echo "Missing $PYTHON. Run ./setup.sh first." >&2; exit 1; }
RUNTIME_DIR="$ROOT/.video-work"
RUNTIME_PATH="$RUNTIME_DIR/web-gui-runtime.json"
LOG_PATH="$RUNTIME_DIR/web-gui.log"
ERROR_LOG_PATH="$RUNTIME_DIR/web-gui-error.log"
mkdir -p "$RUNTIME_DIR"

runtime_pid=""
if [[ -f "$RUNTIME_PATH" ]]; then
  runtime_pid="$("$PYTHON" - "$RUNTIME_PATH" <<'PY'
import json, sys
try:
    print(json.loads(open(sys.argv[1], encoding="utf-8")).get("pid", ""))
except Exception:
    print("")
PY
)"
fi

process_running() {
  [[ -n "$1" ]] || return 1
  kill -0 "$1" 2>/dev/null || return 1
  ps -p "$1" -o command= 2>/dev/null | grep -q "web_gui"
}
if process_running "$runtime_pid"; then
  if [[ "$REPLACE" -ne 1 ]]; then
    echo "LaunchFrame is already running (PID $runtime_pid)."
    echo "Use ./run.sh --replace to restart it."
    exit 0
  fi
  kill "$runtime_pid" 2>/dev/null || true
  for _ in $(seq 1 20); do process_running "$runtime_pid" || break; sleep 0.25; done
  kill -9 "$runtime_pid" 2>/dev/null || true
fi

port_available() {
  "$PYTHON" - "$1" <<'PY'
import socket, sys
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
}
for _ in $(seq 1 50); do
  if port_available "$PORT" && port_available "$WEBSOCKET_PORT"; then break; fi
  PORT=$((PORT + 2))
  WEBSOCKET_PORT=$((WEBSOCKET_PORT + 2))
done
port_available "$PORT" && port_available "$WEBSOCKET_PORT" || { echo "Could not find available ports." >&2; exit 1; }

ARGS=("-m" "web_gui" "--host" "$HOST" "--port" "$PORT" "--websocket-port" "$WEBSOCKET_PORT")
[[ "$DEBUG" -eq 1 ]] && ARGS+=("--debug")
if [[ "$DEBUG" -eq 1 ]]; then
  "$PYTHON" "${ARGS[@]}" >"$LOG_PATH" 2>&1 &
else
  nohup "$PYTHON" "${ARGS[@]}" >>"$LOG_PATH" 2>>"$ERROR_LOG_PATH" </dev/null &
fi
PID=$!

"$PYTHON" - "$RUNTIME_PATH" "$PID" "$HOST" "$PORT" "$WEBSOCKET_PORT" "$ROOT" "$LOG_PATH" "$ERROR_LOG_PATH" <<'PY'
import json, sys
from datetime import datetime, timezone
path, pid, host, port, websocket_port, root, log_path, error_log_path = sys.argv[1:]
data = {
    "pid": int(pid), "host": host, "port": int(port), "websocket_port": int(websocket_port),
    "started_at": datetime.now(timezone.utc).isoformat(), "debug": False,
    "log_path": log_path, "error_log_path": error_log_path, "root": root, "install_root": root,
}
Path = __import__("pathlib").Path
Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

port_open() {
  "$PYTHON" - "$HOST" "$PORT" <<'PY'
import socket, sys
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(0.25)
try:
    sock.connect((sys.argv[1], int(sys.argv[2])))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
}
ready=0
# First run after a fresh install needs extra time: importing Azure SDKs,
# PyMuPDF, python-pptx, etc. and compiling .pyc bytecode caches can take well
# over 15s before the port opens.
for _ in $(seq 1 90); do
  if port_open; then ready=1; break; fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "Web GUI did not become ready. Check $LOG_PATH" >&2
  exit 1
fi
URL="http://$HOST:$PORT/"
echo "LaunchFrame Web GUI: $URL"
echo "PID: $PID"
echo "Log: $LOG_PATH"
if [[ "$NO_BROWSER" -eq 0 ]]; then
  if [[ "$(uname -s)" == "Darwin" ]] && command -v open >/dev/null 2>&1; then open "$URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
  fi
fi
