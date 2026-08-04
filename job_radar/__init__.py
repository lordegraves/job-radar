"""Expose the installed Junior version to every application entry point.

The CLI, web startup messages, diagnostics, and packaging tests use this shared
value so they all report the version installed in the active Python environment.
"""

from importlib.metadata import PackageNotFoundError, version

from job_radar.build_info import BUILD_LABEL, display_version


try:
    # Packaging metadata is the authoritative version source. This keeps the
    # CLI, future About page, and installed application from drifting apart.
    __version__ = version("job-radar")
except PackageNotFoundError:
    # A source checkout may be inspected before Junior has been installed.
    __version__ = "0+unknown"

__build__ = BUILD_LABEL
__display_version__ = display_version(__version__)
