"""Provide shared HTTP handling and consistent safe errors for job collectors."""

from collections.abc import Callable
from typing import Any, TypeVar

import requests


PayloadType = TypeVar("PayloadType")


def get_response(
    url: str,
    *,
    timeout: int,
    params: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    error_type: type[Exception] | None = None,
    request_error_message: str | None = None,
    include_response_body: bool = False,
    request_get: Callable[..., requests.Response] | None = None,
) -> requests.Response:
    request_kwargs: dict[str, Any] = {"timeout": timeout}

    if params is not None:
        request_kwargs["params"] = params

    if headers is not None:
        request_kwargs["headers"] = headers

    if request_get is None:
        request_get = requests.get

    try:
        response = request_get(url, **request_kwargs)
        response.raise_for_status()
    except requests.HTTPError as error:
        if error_type is None or request_error_message is None:
            raise

        message = f"{request_error_message}: {error}"

        if include_response_body:
            response_body = response.text[:500].replace("\n", " ")
            message = f"{message}; response_body={response_body}"

        raise error_type(message) from error
    except requests.RequestException as error:
        if error_type is None or request_error_message is None:
            raise

        raise error_type(f"{request_error_message}: {error}") from error

    return response


def get_json(
    url: str,
    *,
    timeout: int,
    error_type: type[Exception],
    request_error_message: str,
    expected_type: type[PayloadType],
    response_type_error_message: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    invalid_json_error_message: str | None = None,
) -> PayloadType:
    try:
        response = get_response(
            url,
            timeout=timeout,
            params=params,
            headers=headers,
        )
    except requests.RequestException as error:
        raise error_type(f"{request_error_message}: {error}") from error

    try:
        payload: Any = response.json()
    except ValueError as error:
        if invalid_json_error_message is None:
            raise

        raise error_type(invalid_json_error_message) from error

    if not isinstance(payload, expected_type):
        raise error_type(response_type_error_message)

    return payload
