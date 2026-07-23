"""Create and load the installation-local Flask session signing key."""

import os
import secrets
from pathlib import Path


SESSION_SECRET_BYTES = 32
SESSION_SECRET_FILE_NAME = "flask-session.key"


def load_or_create_session_secret(database_path: str | Path) -> bytes:
    """Return a stable secret stored beside other user-owned runtime data."""

    secret_path = (
        Path(database_path).expanduser().resolve().parent
        / "runtime"
        / SESSION_SECRET_FILE_NAME
    )
    secret_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        secret = secret_path.read_bytes()
    except FileNotFoundError:
        secret = secrets.token_bytes(SESSION_SECRET_BYTES)
        try:
            descriptor = os.open(
                secret_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            secret = secret_path.read_bytes()
        else:
            with os.fdopen(descriptor, "wb") as secret_file:
                secret_file.write(secret)
                secret_file.flush()
                os.fsync(secret_file.fileno())

    if len(secret) < SESSION_SECRET_BYTES:
        raise RuntimeError("Junior's session signing key is invalid.")

    return secret
