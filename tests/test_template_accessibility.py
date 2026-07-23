"""Protect shared keyboard semantics and accessible table descriptions."""

import re
from html.parser import HTMLParser
from pathlib import Path


TEMPLATE_ROOT = Path("job_radar/templates")


class _FormControlParser(HTMLParser):
    """Collect visible controls that have no programmatic label."""

    def __init__(self, template: str) -> None:
        super().__init__()
        self.template = template
        self.label_depth = 0
        self.unlabeled: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        if tag == "label":
            self.label_depth += 1
            return
        if tag not in {"input", "select", "textarea"}:
            return
        if attributes.get("type") == "hidden":
            return
        control_id = attributes.get("id")
        has_explicit_label = bool(
            control_id
            and re.search(
                rf'<label\b[^>]*for=["\']{re.escape(control_id)}["\']',
                self.template,
            )
        )
        if (
            self.label_depth == 0
            and not has_explicit_label
            and "aria-label" not in attributes
            and "aria-labelledby" not in attributes
        ):
            self.unlabeled.append(
                attributes.get("name")
                or control_id
                or f"unnamed {tag}"
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "label":
            self.label_depth -= 1


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


def test_every_visible_form_control_has_a_programmatic_label() -> None:
    unlabeled_controls: list[str] = []

    for template_path in TEMPLATE_ROOT.rglob("*.html"):
        template = template_path.read_text(encoding="utf-8")
        parser = _FormControlParser(template)
        parser.feed(template)
        unlabeled_controls.extend(
            f"{template_path.as_posix()}: {control}"
            for control in parser.unlabeled
        )

    assert unlabeled_controls == []


def _relative_luminance(color: str) -> float:
    channels = [
        int(color[index : index + 2], 16) / 255
        for index in (0, 2, 4)
    ]
    linear = [
        value / 12.92
        if value <= 0.04045
        else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground: str, background: str) -> float:
    values = sorted(
        (
            _relative_luminance(foreground),
            _relative_luminance(background),
        ),
        reverse=True,
    )
    return (values[0] + 0.05) / (values[1] + 0.05)


def test_shared_text_colors_meet_normal_text_contrast() -> None:
    color_pairs = (
        ("f3f3f3", "0f0f10"),
        ("b7b7c2", "1f1f23"),
        ("60cdff", "1f1f23"),
        ("ffffff", "0078d4"),
        ("ffffff", "106ebe"),
        ("ffffff", "b4232a"),
        ("ffffff", "8f1d22"),
        ("8fdc8f", "1f1f23"),
        ("ffb86c", "1f1f23"),
        ("f7c948", "1f1f23"),
    )

    assert all(
        _contrast_ratio(foreground, background) >= 4.5
        for foreground, background in color_pairs
    )


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
