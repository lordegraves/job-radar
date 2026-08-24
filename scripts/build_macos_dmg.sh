#!/bin/sh
# Build on macOS because PyInstaller application bundles are host-specific.
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python_path="$project_root/.venv/bin/python"
build_root="$project_root/build/macos"
artifact_root="$project_root/artifacts/macos"
iconset="$build_root/Junior.iconset"
icon_source="$project_root/job_radar/static/junior_icon_v2.png"
app_path="$build_root/dist/Junior.app"
staging_root="$build_root/dmg"
architecture=$(uname -m)
artifact_path="$artifact_root/Junior-0.2.0-RC6-build-1.25-macos-$architecture.dmg"

if [ "$(uname -s)" != "Darwin" ]; then
    echo "The macOS package must be built on macOS." >&2
    exit 1
fi
if [ ! -x "$python_path" ]; then
    echo "Repository-local macOS Python was not found: $python_path" >&2
    exit 1
fi
if [ ! -f "$icon_source" ]; then
    echo "Junior's source icon was not found: $icon_source" >&2
    exit 1
fi

rm -rf "$build_root" "$artifact_root"
mkdir -p "$iconset" "$artifact_root"

for size in 16 32 128 256 512; do
    double_size=$((size * 2))
    sips -z "$size" "$size" "$icon_source" \
        --out "$iconset/icon_${size}x${size}.png" >/dev/null
    sips -z "$double_size" "$double_size" "$icon_source" \
        --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$iconset" -o "$build_root/Junior.icns"

"$python_path" -m PyInstaller --clean --noconfirm \
    --workpath "$build_root/pyinstaller" \
    --distpath "$build_root/dist" \
    "$project_root/packaging/macos/junior.spec"

if [ ! -d "$app_path" ]; then
    echo "PyInstaller did not create Junior.app." >&2
    exit 1
fi

# Local field-test builds use an ad-hoc signature. Public distribution still
# requires an approved Developer ID certificate and Apple notarization.
codesign --force --deep --sign - "$app_path"
codesign --verify --deep --strict "$app_path"

mkdir -p "$staging_root"
cp -R "$app_path" "$staging_root/Junior.app"
ln -s /Applications "$staging_root/Applications"

hdiutil create \
    -volname "Junior RC6 Build 1.25" \
    -srcfolder "$staging_root" \
    -ov \
    -format UDZO \
    "$artifact_path" >/dev/null

echo "macOS application created: $app_path"
echo "macOS installer created: $artifact_path"
echo "Drag Junior.app to Applications after opening the DMG."
