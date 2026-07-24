#!/usr/bin/env sh
# Launch the bundled application without changing Junior's user-data location.
set -eu

bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ "$(uname -s)" != "Linux" ]; then
    echo "This Junior package is for Linux." >&2
    exit 1
fi

if [ ! -x "$bundle_dir/junior" ]; then
    echo "Junior's executable is missing or is not executable." >&2
    exit 1
fi

if ! command -v ldconfig >/dev/null 2>&1; then
    echo "Junior cannot verify Linux desktop-library dependencies." >&2
elif ! ldconfig -p 2>/dev/null | grep -Eq 'libwebkit2gtk|libwebkitgtk'; then
    echo "Junior needs a WebKit GTK desktop library. Install your distribution's webkit2gtk package and try again." >&2
    exit 1
fi

exec "$bundle_dir/junior" "$@"
