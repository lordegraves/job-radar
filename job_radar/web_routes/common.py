from datetime import date

from flask import request


def matches_filter_value(
    value: str | None,
    selected_filter: str,
) -> bool:
    if value is None:
        return False

    return value.strip().casefold() == selected_filter.strip().casefold()


def parse_sort_date(value: str | None) -> date | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def normalize_optional_form_value(field_name: str) -> str | None:
    value = request.form.get(field_name, "").strip()

    if not value:
        return None

    return value
