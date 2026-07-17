from importlib.metadata import PackageNotFoundError, version


try:
    # Packaging metadata is the authoritative version source. This keeps the
    # CLI, future About page, and installed application from drifting apart.
    __version__ = version("job-radar")
except PackageNotFoundError:
    # A source checkout may be inspected before Job Radar has been installed.
    __version__ = "0+unknown"
