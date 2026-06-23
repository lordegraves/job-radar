from job_radar.normalize import clean_text, make_canonical_key, make_content_hash, normalize_for_key


def test_clean_text_removes_extra_whitespace() -> None:
    assert clean_text("  Senior   Infrastructure\nEngineer  ") == "Senior Infrastructure Engineer"


def test_clean_text_handles_none() -> None:
    assert clean_text(None) == ""


def test_normalize_for_key_lowercases_and_replaces_punctuation() -> None:
    assert normalize_for_key("Senior Infrastructure Engineer!") == "senior-infrastructure-engineer"


def test_make_canonical_key_includes_company_title_and_location() -> None:
    result = make_canonical_key(
        company_key="example_ai",
        title="Senior Infrastructure Engineer",
        location="Remote - US",
    )

    assert result == "example-ai:senior-infrastructure-engineer:remote-us"


def test_make_canonical_key_omits_empty_location() -> None:
    result = make_canonical_key(
        company_key="example_ai",
        title="Senior Infrastructure Engineer",
        location=None,
    )

    assert result == "example-ai:senior-infrastructure-engineer"


def test_make_content_hash_is_stable_for_same_content() -> None:
    first = make_content_hash(
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure",
        salary_text="$180k - $220k",
    )

    second = make_content_hash(
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure",
        salary_text="$180k - $220k",
    )

    assert first == second


def test_make_content_hash_changes_when_description_changes() -> None:
    first = make_content_hash(
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux infrastructure",
    )

    second = make_content_hash(
        title="Senior Infrastructure Engineer",
        location="Remote",
        description="Build Linux and Kubernetes infrastructure",
    )

    assert first != second