#!/usr/bin/env sh
# Build on Linux because PyInstaller bundles are specific to their host OS.
set -eu

project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python_path="$project_root/.venv/bin/python"
build_root="$project_root/build/linux"
artifact_root="$project_root/artifacts/linux"
bundle_root="$build_root/Junior"

if [ "$(uname -s)" != "Linux" ]; then
    echo "The Linux package must be built on Linux." >&2
    exit 1
fi
if [ ! -x "$python_path" ]; then
    echo "Repository-local Linux Python was not found: $python_path" >&2
    exit 1
fi

"$python_path" -m PyInstaller --clean --noconfirm \
    --workpath "$build_root/pyinstaller" \
    --distpath "$build_root/dist" \
    "$project_root/packaging/linux/junior.spec"

rm -rf "$bundle_root"
cp -R "$build_root/dist/Junior" "$bundle_root"
cp "$project_root/packaging/linux/launch-junior.sh" "$bundle_root/"
cp "$project_root/packaging/linux/install.sh" "$bundle_root/"
cp "$project_root/packaging/linux/uninstall.sh" "$bundle_root/"
chmod +x "$bundle_root/junior" "$bundle_root/"*.sh

mkdir -p "$artifact_root"
tar -C "$build_root" -czf "$artifact_root/Junior-linux-x86_64.tar.gz" Junior
echo "Linux tarball created: $artifact_root/Junior-linux-x86_64.tar.gz"
