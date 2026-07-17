from typing import Any, TypeVar

import requests


PayloadType = TypeVar("PayloadType")


def get_json(
    url: str,
    *,
    timeout: int,
    error_type: type[Exception],
    request_error_message: str,
    expected_type: type[PayloadType],
    response_type_error_message: str,
) -> PayloadType:
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as error:
        raise error_type(f"{request_error_message}: {error}") from error

    payload: Any = response.json()

    if not isinstance(payload, expected_type):
        raise error_type(response_type_error_message)

    return payload