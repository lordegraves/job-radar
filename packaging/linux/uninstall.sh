#!/usr/bin/env sh
# Remove application-owned files while deliberately preserving all user data.
set -eu

install_dir="${XDG_DATA_HOME:-$HOME/.local/share}/junior/application"
launcher="${HOME}/.local/bin/junior"

if [ -L "$launcher" ] && [ "$(readlink "$launcher")" = "$install_dir/launch-junior.sh" ]; then
    rm "$launcher"
fi

if [ -d "$install_dir" ]; then
    rm -rf "$install_dir"
fi

echo "Junior application files were removed."
echo "Profiles, resumes, settings, databases, reports, logs, backups, schedules, and credentials were preserved."
