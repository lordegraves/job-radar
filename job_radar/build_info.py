"""Keep the tester-facing release-candidate build label in one place."""

RELEASE_CANDIDATE = 5
BUILD_NUMBER = 1
BUILD_LABEL = f"RC{RELEASE_CANDIDATE} Build {BUILD_NUMBER}"
BUILD_SLUG = f"RC{RELEASE_CANDIDATE}-build-{BUILD_NUMBER}"


def display_version(application_version: str) -> str:
    """Combine the package version with the exact field-test build."""

    return f"{application_version} — {BUILD_LABEL}"
