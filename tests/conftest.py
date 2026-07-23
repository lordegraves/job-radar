"""Provide shared web-test behavior without weakening production safeguards."""

import secrets

import pytest
from flask.testing import FlaskClient

from job_radar.csrf import (
    CSRF_HEADER_NAME,
    CSRF_SESSION_KEY,
)


@pytest.fixture(autouse=True)
def submit_valid_csrf_tokens(monkeypatch):
    """Make existing route tests submit a real session-bound CSRF token."""

    original_post = FlaskClient.post

    def protected_post(client, *args, **kwargs):
        without_csrf = kwargs.pop("_without_csrf", False)
        if not without_csrf:
            with client.session_transaction() as current_session:
                token = current_session.get(CSRF_SESSION_KEY)
                if not isinstance(token, str) or not token:
                    token = secrets.token_urlsafe(32)
                    current_session[CSRF_SESSION_KEY] = token

            headers = dict(kwargs.get("headers") or {})
            headers.setdefault(CSRF_HEADER_NAME, token)
            kwargs["headers"] = headers

        return original_post(client, *args, **kwargs)

    monkeypatch.setattr(FlaskClient, "post", protected_post)
