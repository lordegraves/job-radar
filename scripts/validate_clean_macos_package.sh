#!/bin/sh
# Validate the built application without accessing the operator's Junior data.
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
architecture=$(uname -m)
dmg_path="$project_root/artifacts/macos/Junior-0.2.0-RC6-build-1.25-macos-$architecture.dmg"
mount_point=$(mktemp -d /tmp/junior-macos-mount.XXXXXX)
user_data_root=$(mktemp -d /tmp/junior-macos-data.XXXXXX)
response_path=$(mktemp /tmp/junior-macos-response.XXXXXX)
server_pid=""

cleanup() {
    if [ -n "$server_pid" ]; then
        kill "$server_pid" 2>/dev/null || true
        wait "$server_pid" 2>/dev/null || true
    fi
    hdiutil detach "$mount_point" -quiet 2>/dev/null || true
    rm -rf "$mount_point" "$user_data_root"
    rm -f "$response_path"
}
trap cleanup EXIT INT TERM

if [ "$(uname -s)" != "Darwin" ]; then
    echo "The macOS package must be validated on macOS." >&2
    exit 1
fi
if [ ! -f "$dmg_path" ]; then
    echo "Built DMG was not found: $dmg_path" >&2
    exit 1
fi

hdiutil attach "$dmg_path" -mountpoint "$mount_point" -nobrowse -readonly -quiet
app_path="$mount_point/Junior.app"
executable="$app_path/Contents/MacOS/Junior"

test -x "$executable"
test -f "$app_path/Contents/Resources/Junior.icns"
test "$(defaults read "$app_path/Contents/Info" CFBundleIdentifier)" = \
    "com.claytongraves.junior"
test "$(defaults read "$app_path/Contents/Info" CFBundleShortVersionString)" = \
    "0.2.0"
codesign --verify --deep --strict "$app_path"

for private_name in config data logs profiles reports resumes; do
    if find "$app_path" -type d -name "$private_name" -print -quit | grep -q .; then
        echo "Private runtime directory was packaged: $private_name" >&2
        exit 1
    fi
done

JOB_RADAR_DATA_DIR="$user_data_root" \
    "$executable" --no-browser --port 5051 >/dev/null 2>&1 &
server_pid=$!

attempt=0
ready=false
while [ "$attempt" -lt 90 ]; do
    if curl -fsSL --connect-timeout 1 --max-time 2 \
        http://127.0.0.1:5051/ -o "$response_path" 2>/dev/null; then
        ready=true
        break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
        echo "Packaged Junior exited before becoming ready." >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    sleep 1
done

if [ "$ready" != true ]; then
    echo "Packaged Junior did not become ready within 90 seconds." >&2
    exit 1
fi

grep -q "RC6 Build 1.25" "$response_path"
test -f "$user_data_root/data/job_radar.sqlite3"
test -f "$user_data_root/config/settings.yaml"

echo "Clean macOS package validation passed."
