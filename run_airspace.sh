#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
SCENE_DIR="$FRONTEND_DIR/assets/flight-map-3d"
LOG_DIR="${TMPDIR:-/tmp}/airspace-dev-logs"
API_LOG="$LOG_DIR/backend.log"
SCENE_LOG="$LOG_DIR/scene.log"

case "$(uname -s)" in
    Linux) DEFAULT_DEVICE="linux" ;;
    Darwin) DEFAULT_DEVICE="macos" ;;
    *) DEFAULT_DEVICE="windows" ;;
 esac
DEVICE_ID="${DEFAULT_DEVICE}"
DEV_HOST="${AIRSPACE_DEV_HOST:-}"
BACKEND_PID=""
SCENE_PID=""

usage() {
    cat <<'EOF'
Usage: ./run_airspace.sh [--device DEVICE_ID] [--host HOST]

Examples:
  ./run_airspace.sh --device linux
  ./run_airspace.sh --device windows
  ./run_airspace.sh --device chrome
  ./run_airspace.sh --device emulator-5554
  ./run_airspace.sh --device <device-id> --host 192.168.1.25

The launcher defaults to Linux on Linux hosts, macOS on macOS hosts, and
Windows on Windows hosts. The host override is for a physical phone on the
same LAN; Android emulators default to 10.0.2.2 and other devices default to
localhost.
EOF
}

while (($#)); do
    case "$1" in
        --device)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            DEVICE_ID="$2"
            shift 2
            ;;
        --host)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            DEV_HOST="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$DEV_HOST" ]]; then
    case "$DEVICE_ID" in
        emulator-*|*android*) DEV_HOST="10.0.2.2" ;;
        *) DEV_HOST="localhost" ;;
    esac
fi

if [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
    PYTHON="$BACKEND_DIR/.venv/bin/python"
elif [[ -x "$BACKEND_DIR/venv/bin/python" ]]; then
    PYTHON="$BACKEND_DIR/venv/bin/python"
elif [[ -x "$BACKEND_DIR/.venv/Scripts/python.exe" ]]; then
    PYTHON="$BACKEND_DIR/.venv/Scripts/python.exe"
else
    printf 'Backend virtual environment not found. Create it from the repository root, for example:\n' >&2
    printf '  python3 -m venv backend/.venv\n' >&2
    printf '  backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt\n' >&2
    exit 1
fi

if [[ ! -d "$SCENE_DIR/node_modules" ]]; then
    printf 'Three.js dependencies are missing. Run npm ci in %s.\n' "$SCENE_DIR" >&2
    exit 1
fi
for command_name in curl npm flutter; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Required command not found: %s\n' "$command_name" >&2
        exit 1
    fi
done

mkdir -p "$LOG_DIR"

service_ready() {
    curl --fail --silent --show-error --max-time 2 "$1" >/dev/null 2>&1
}

wait_for_service() {
    local url="$1"
    local pid="$2"
    local name="$3"
    local log_file="$4"
    local attempt

    for ((attempt = 0; attempt < 30; attempt++)); do
        if service_ready "$url"; then
            return 0
        fi
        if ! kill -0 "$pid" 2>/dev/null; then
            printf '%s stopped before becoming ready. Log: %s\n' "$name" "$log_file" >&2
            tail -n 80 "$log_file" >&2 || true
            return 1
        fi
        sleep 1
    done

    printf '%s did not become ready at %s. Log: %s\n' "$name" "$url" "$log_file" >&2
    tail -n 80 "$log_file" >&2 || true
    return 1
}

stop_process_tree() {
    local pid="$1"
    local child_pid

    [[ -n "$pid" ]] || return 0
    if command -v pgrep >/dev/null 2>&1; then
        while read -r child_pid; do
            [[ -n "$child_pid" ]] && stop_process_tree "$child_pid"
        done < <(pgrep -P "$pid" 2>/dev/null || true)
    fi
    kill "$pid" 2>/dev/null || true
}

cleanup() {
    local status=$?
    trap - EXIT
    stop_process_tree "$SCENE_PID"
    stop_process_tree "$BACKEND_PID"
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

export AIRSPACE_CORS_ORIGINS="http://${DEV_HOST}:5173"

if service_ready 'http://127.0.0.1:8000/health'; then
    printf 'Reusing backend at http://127.0.0.1:8000\n'
    if [[ "$DEV_HOST" != localhost && "$DEV_HOST" != 127.0.0.1 && "$DEV_HOST" != 10.0.2.2 ]]; then
        printf 'Note: a reused backend must have AIRSPACE_CORS_ORIGINS=http://%s:5173 set for this host.\n' "$DEV_HOST"
    fi
else
    (
        cd "$BACKEND_DIR"
        AIRSPACE_CORS_ORIGINS="$AIRSPACE_CORS_ORIGINS" \
            "$PYTHON" -m uvicorn main:app --host 0.0.0.0 --port 8000
    ) >"$API_LOG" 2>&1 &
    BACKEND_PID=$!
    wait_for_service 'http://127.0.0.1:8000/health' "$BACKEND_PID" 'Backend' "$API_LOG"
    printf 'Backend ready at http://127.0.0.1:8000\n'
fi

if service_ready 'http://127.0.0.1:5173/'; then
    printf 'Reusing Three.js dev server at http://127.0.0.1:5173\n'
else
    (
        cd "$SCENE_DIR"
        npm run dev -- --host 0.0.0.0 --strictPort
    ) >"$SCENE_LOG" 2>&1 &
    SCENE_PID=$!
    wait_for_service 'http://127.0.0.1:5173/' "$SCENE_PID" 'Three.js dev server' "$SCENE_LOG"
    printf 'Three.js ready at http://127.0.0.1:5173\n'
fi

printf 'Starting Flutter on %s (scene/API host: %s). Ctrl+C stops Flutter and services started here.\n' \
    "$DEVICE_ID" "$DEV_HOST"
cd "$FRONTEND_DIR"
flutter run -d "$DEVICE_ID" "--dart-define=AIRSPACE_DEV_HOST=$DEV_HOST"