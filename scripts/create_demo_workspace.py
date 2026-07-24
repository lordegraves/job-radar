"""Create a fictional Junior workspace for screenshots and release checks."""

import argparse
from pathlib import Path

from job_radar.demo_workspace import (
    DemoWorkspaceError,
    create_demo_workspace,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an isolated fictional Junior demo workspace."
    )
    parser.add_argument(
        "destination",
        type=Path,
        help="New directory to create; existing paths are refused.",
    )
    arguments = parser.parse_args()

    try:
        paths = create_demo_workspace(arguments.destination)
    except DemoWorkspaceError as error:
        parser.error(str(error))

    print(f"Fictional Junior demo created: {paths.root}")
    print(f"Settings: {paths.config / 'settings.yaml'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
