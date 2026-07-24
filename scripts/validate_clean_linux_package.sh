#!/usr/bin/env sh
# Exercise only the Linux release archive in a Python-free disposable system.
set -eu

archive=/input/Junior-linux-x86_64.tar.gz
validation_root=/tmp/junior-clean-linux
home_root="$validation_root/home"
work_root="$validation_root/work"

if command -v python >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
    echo "The clean Linux image unexpectedly contains Python." >&2
    exit 1
fi
if [ ! -f "$archive" ]; then
    echo "The Linux release archive was not mounted." >&2
    exit 1
fi

mkdir -p "$home_root" "$work_root"
tar -xzf "$archive" -C "$work_root"

HOME="$home_root" sh "$work_root/Junior/install.sh"
installed_root="$home_root/.local/share/junior/application"
HOME="$home_root" "$installed_root/junior" --help >/dev/null

data_root="$home_root/.local/share/job-radar"
config_root="$home_root/.config/job-radar"
mkdir -p "$data_root" "$config_root"
printf '%s\n' preserve > "$data_root/clean-package-sentinel.txt"
printf '%s\n' preserve > "$config_root/clean-package-sentinel.txt"

HOME="$home_root" sh "$work_root/Junior/uninstall.sh"

test ! -e "$installed_root"
test ! -e "$home_root/.local/bin/junior"
test "$(cat "$data_root/clean-package-sentinel.txt")" = preserve
test "$(cat "$config_root/clean-package-sentinel.txt")" = preserve

echo "Clean Linux package validation passed."
