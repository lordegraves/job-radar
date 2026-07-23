"""Protect every state-changing web request with a session-bound token."""

import secrets
from hmac import compare_digest

from flask import Flask, jsonify, render_template, request, session


CSRF_FIELD_NAME = "_csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_SESSION_KEY = "csrf_token"


def generate_csrf_token() -> str:
    """Return the current session token, creating one when needed."""

    token = session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def register_csrf_protection(app: Flask) -> None:
    """Register shared token rendering and POST validation."""

    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.before_request
    def validate_csrf_token():
        if request.method != "POST":
            return None

        expected_token = session.get(CSRF_SESSION_KEY)
        submitted_token = (
            request.form.get(CSRF_FIELD_NAME)
            or request.headers.get(CSRF_HEADER_NAME)
        )
        if (
            not isinstance(expected_token, str)
            or not isinstance(submitted_token, str)
            or not compare_digest(expected_token, submitted_token)
        ):
            if request.accept_mimetypes.best == "application/json":
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": (
                                "Junior could not safely submit this request. "
                                "Refresh the page and try again."
                            ),
                        }
                    ),
                    400,
                )

            return (
                render_template("mutation_error.html"),
                400,
            )

        return None
