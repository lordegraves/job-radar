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
