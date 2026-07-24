#!/usr/bin/env sh
# Install only application-owned files under the current user's home directory.
set -eu

source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install_dir="${XDG_DATA_HOME:-$HOME/.local/share}/junior/application"
bin_dir="${HOME}/.local/bin"

mkdir -p "$install_dir" "$bin_dir"
cp -R "$source_dir/." "$install_dir/"
chmod +x "$install_dir/junior" "$install_dir/launch-junior.sh"
ln -sfn "$install_dir/launch-junior.sh" "$bin_dir/junior"

echo "Junior was installed for this user."
echo "Launch it with: $bin_dir/junior"
echo "User data remains separate under Junior's normal Linux data directories."
