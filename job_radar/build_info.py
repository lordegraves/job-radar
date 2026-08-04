"""Keep the tester-facing release-candidate build label in one place."""

RELEASE_LABEL = "RC6"
BUILD_NUMBER = "1.12"
RELEASE_TAG = "v0.2.0-rc6"
BUILD_LABEL = f"{RELEASE_LABEL} Build {BUILD_NUMBER}"
BUILD_SLUG = f"{RELEASE_LABEL}-build-{BUILD_NUMBER}"


def display_version(application_version: str) -> str:
    """Combine the package version with the exact field-test build."""

    return f"{application_version} — {BUILD_LABEL}"
