"""Protect shared keyboard semantics and accessible table descriptions."""

import re
from pathlib import Path


TEMPLATE_ROOT = Path("job_radar/templates")


def test_every_html_table_has_an_accessible_caption() -> None:
    missing_captions: list[str] = []

    for template_path in TEMPLATE_ROOT.rglob("*.html"):
        template = template_path.read_text(encoding="utf-8")
        for table_number, table in enumerate(
            re.findall(r"<table\b.*?</table>", template, flags=re.DOTALL),
            start=1,
        ):
            if "<caption" not in table:
                missing_captions.append(
                    f"{template_path.as_posix()} table {table_number}"
                )

    assert missing_captions == []


def test_shared_shell_has_keyboard_and_scaling_boundaries() -> None:
    template = (TEMPLATE_ROOT / "base.html").read_text(encoding="utf-8")

    assert 'name="viewport"' in template
    assert 'class="skip-link" href="#main-content"' in template
    assert 'id="main-content"' in template
    assert ":focus-visible" in template
    assert 'aria-current="page"' in template


def test_profile_suggestions_expose_and_support_keyboard_navigation() -> None:
    template = (TEMPLATE_ROOT / "preferences.html").read_text(encoding="utf-8")

    assert 'aria-controls="occupation-suggestions"' in template
    assert 'aria-controls="location-suggestions"' in template
    assert template.count('aria-expanded="false"') == 2
    assert 'role="listbox"' not in template
    assert 'event.key === "ArrowDown"' in template
    assert 'event.key === "Escape"' in template


def test_destructive_application_actions_use_user_facing_language() -> None:
    tracker_template = (TEMPLATE_ROOT / "tracker_edit.html").read_text(
        encoding="utf-8"
    )
    history_template = (TEMPLATE_ROOT / "history_edit.html").read_text(
        encoding="utf-8"
    )

    assert "tracker row" not in tracker_template
    assert "terminal quick action" not in tracker_template
    assert "Permanently delete this application?" in tracker_template
    assert "Delete application" in tracker_template
    assert "history row" not in history_template
    assert "Permanently delete this application history record?" in (
        history_template
    )
    assert "This cannot be undone." in history_template
