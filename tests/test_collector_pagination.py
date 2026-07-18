"""Tests shared collector page limits and protection from invalid settings."""

from job_radar.collectors.pagination import (
    ABSOLUTE_MAX_PAGES,
    get_max_pages,
    get_page_size,
)


def test_get_page_size_uses_default_for_invalid_values() -> None:
    assert get_page_size({}, default=20) == 20
    assert get_page_size({"page_size": "invalid"}, default=20) == 20
    assert get_page_size({"page_size": 0}, default=20) == 20
    assert get_page_size({"page_size": -5}, default=20) == 20


def test_get_page_size_accepts_positive_integer_text() -> None:
    assert get_page_size({"page_size": "40"}, default=20) == 40


def test_get_max_pages_uses_default_for_invalid_values() -> None:
    assert get_max_pages({}, default=10) == 10
    assert get_max_pages({"max_pages": "invalid"}, default=10) == 10
    assert get_max_pages({"max_pages": 0}, default=10) == 10
    assert get_max_pages({"max_pages": -1}, default=10) == 10


def test_get_max_pages_enforces_absolute_ceiling() -> None:
    assert (
        get_max_pages(
            {"max_pages": ABSOLUTE_MAX_PAGES + 500},
            default=10,
        )
        == ABSOLUTE_MAX_PAGES
    )
