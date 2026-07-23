"""Keep Administration mode explicit, session-scoped, and locally routed."""

from collections.abc import Callable
from functools import wraps
from urllib.parse import unquote, urlsplit

from flask import current_app, redirect, request, session, url_for


ADMIN_SESSION_KEY = "admin_unlocked"


def is_admin_unlocked() -> bool:
    """Return whether this browser session unlocked the current Junior run."""

    marker = current_app.config.get("JOB_RADAR_ADMIN_SESSION_MARKER")
    return bool(marker) and session.get(ADMIN_SESSION_KEY) == marker


def unlock_admin_session() -> None:
    """Unlock Administration for this browser and current Junior process."""

    session[ADMIN_SESSION_KEY] = current_app.config[
        "JOB_RADAR_ADMIN_SESSION_MARKER"
    ]


def lock_admin_session() -> None:
    """Remove Administration state from the current browser session."""

    session.pop(ADMIN_SESSION_KEY, None)


def safe_local_path(value: str | None) -> str | None:
    """Return a local absolute path, rejecting external or ambiguous targets."""

    if not value:
        return None

    parsed = urlsplit(value)
    decoded_path = unquote(parsed.path)
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
        or decoded_path.startswith("//")
        or "\\" in decoded_path
        or any(ord(character) < 32 for character in value)
    ):
        return None

    return value


def administration_required(view: Callable) -> Callable:
    """Redirect locked sessions to the Administration unlock page."""

    @wraps(view)
    def guarded_view(*args, **kwargs):
        if not is_admin_unlocked():
            return_path = request.full_path.rstrip("?")
            return redirect(
                url_for(
                    "administration_unlock",
                    next=safe_local_path(return_path),
                )
            )
        return view(*args, **kwargs)

    return guarded_view
