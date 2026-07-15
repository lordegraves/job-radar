from typing import Any


ABSOLUTE_MAX_PAGES = 100


def get_positive_int(
    company_config: dict[str, Any],
    *,
    key: str,
    default: int,
    maximum: int | None = None,
) -> int:
    value = company_config.get(key, default)

    try:
        parsed_value = int(value)
    except (TypeError, ValueError):
        parsed_value = default

    if parsed_value <= 0:
        parsed_value = default

    if maximum is not None:
        parsed_value = min(parsed_value, maximum)

    return parsed_value


def get_page_size(
    company_config: dict[str, Any],
    *,
    default: int,
) -> int:
    return get_positive_int(
        company_config,
        key="page_size",
        default=default,
    )


def get_max_pages(
    company_config: dict[str, Any],
    *,
    default: int,
) -> int:
    return get_positive_int(
        company_config,
        key="max_pages",
        default=default,
        maximum=ABSOLUTE_MAX_PAGES,
    )
