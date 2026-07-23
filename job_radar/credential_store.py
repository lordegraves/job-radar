"""Store secrets only through the operating system's credential manager."""

from typing import Protocol

import keyring
from keyring.errors import KeyringError, PasswordDeleteError


SERVICE_NAME = "junior"


class CredentialStoreError(RuntimeError):
    """Explain that secure credential storage is unavailable without secrets."""


class CredentialBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


def store_credential(
    reference: str,
    secret: str,
    *,
    backend: CredentialBackend | None = None,
) -> None:
    """Store one non-empty secret under a non-secret stable reference."""

    _validate_reference(reference)
    if not secret:
        raise CredentialStoreError("Enter a credential before saving.")
    try:
        (backend or keyring).set_password(SERVICE_NAME, reference, secret)
    except KeyringError as error:
        raise CredentialStoreError(
            "The operating-system credential manager is unavailable."
        ) from error


def get_credential(
    reference: str,
    *,
    backend: CredentialBackend | None = None,
) -> str | None:
    """Read a secret without displaying or persisting it elsewhere."""

    _validate_reference(reference)
    try:
        return (backend or keyring).get_password(SERVICE_NAME, reference)
    except KeyringError as error:
        raise CredentialStoreError(
            "The operating-system credential manager is unavailable."
        ) from error


def delete_credential(
    reference: str,
    *,
    backend: CredentialBackend | None = None,
) -> bool:
    """Remove one credential while treating an absent entry as already clear."""

    _validate_reference(reference)
    try:
        (backend or keyring).delete_password(SERVICE_NAME, reference)
    except PasswordDeleteError:
        return False
    except KeyringError as error:
        raise CredentialStoreError(
            "The operating-system credential manager is unavailable."
        ) from error
    return True


def _validate_reference(reference: str) -> None:
    if not reference.strip() or len(reference) > 200:
        raise CredentialStoreError("Choose a valid credential reference.")
