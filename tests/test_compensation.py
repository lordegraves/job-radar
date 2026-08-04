"""Tests salary parsing and comparison with the candidate's compensation floor."""

from job_radar.compensation import (
    evaluate_compensation,
    extract_annual_compensation_text,
    parse_salary_range_usd,
)


def test_parse_salary_range_usd_handles_k_range() -> None:
    assert parse_salary_range_usd("$180K - $220K") == (180000, 220000)


def test_parse_salary_range_usd_handles_decimal_annual_range() -> None:
    assert parse_salary_range_usd("70245.00 To 105420.00 (USD) Annually") == (
        70245,
        105420,
    )


def test_parse_salary_range_usd_handles_jibe_range() -> None:
    assert parse_salary_range_usd(
        "USD $126,490.00/Yr. | USD $180,700.00/Yr."
    ) == (126490, 180700)


def test_parse_salary_range_usd_ignores_hourly_ranges() -> None:
    assert parse_salary_range_usd("$75/hr - $95/hr") == (None, None)


def test_evaluate_compensation_meets_floor_when_min_is_above_floor() -> None:
    result = evaluate_compensation("$180K - $220K", 160000)

    assert result.label == "Meets floor"
    assert result.range_label == "$180,000 - $220,000"
    assert result.min_usd == 180000
    assert result.max_usd == 220000


def test_evaluate_compensation_below_floor_when_max_is_below_floor() -> None:
    result = evaluate_compensation("70245.00 To 105420.00 (USD) Annually", 160000)

    assert result.label == "Below floor"
    assert result.range_label == "$70,245 - $105,420"
    assert result.min_usd == 70245
    assert result.max_usd == 105420


def test_evaluate_compensation_partial_range_meets_floor_when_range_overlaps_floor() -> None:
    result = evaluate_compensation("USD $126,490.00/Yr. | USD $180,700.00/Yr.", 160000)

    assert result.label == "Partial range meets floor"
    assert result.range_label == "$126,490 - $180,700"
    assert result.min_usd == 126490
    assert result.max_usd == 180700


def test_evaluate_compensation_partial_range_meets_floor_when_max_equals_floor() -> None:
    result = evaluate_compensation("$120K - $160K", 160000)

    assert result.label == "Partial range meets floor"
    assert result.range_label == "$120,000 - $160,000"
    assert result.min_usd == 120000
    assert result.max_usd == 160000


def test_evaluate_compensation_unknown_without_salary_text() -> None:
    result = evaluate_compensation(None, 160000)

    assert result.label == "Unknown"
    assert result.range_label == "Unknown"
    assert result.min_usd is None
    assert result.max_usd is None


def test_extract_annual_compensation_from_description() -> None:
    description = (
        "The annual compensation range for this position is "
        "$170,000 - $210,000 per year."
    )

    extracted = extract_annual_compensation_text(description)

    assert extracted is not None
    assert evaluate_compensation(extracted, 160000).label == "Meets floor"


def test_extract_annual_compensation_reads_annual_salary_heading() -> None:
    extracted = extract_annual_compensation_text(
        "The annual compensation range is listed below.\n"
        "Annual Salary:\n$325,000 - $360,000 USD"
    )

    assert extracted == "Annual Salary: $325,000 - $360,000 USD"


def test_extract_annual_compensation_reads_standalone_usd_range() -> None:
    extracted = extract_annual_compensation_text(
        "Salary Range</p><p>$200,000 — $225,000 USD</p>"
    )

    assert evaluate_compensation(extracted, 160000).range_label == (
        "$200,000 - $225,000"
    )


def test_extract_annual_compensation_preserves_multiple_level_ranges() -> None:
    extracted = extract_annual_compensation_text(
        "Level III annual salary: $118,000 - $161,000 USD. "
        "Level IV annual salary: $142,000 - $194,000 USD."
    )

    assert extracted is not None
    assert "$118,000 - $161,000" in extracted
    assert "$142,000 - $194,000" in extracted
    assert evaluate_compensation(extracted, 160000).range_label == (
        "$118,000 - $194,000"
    )


def test_extract_annual_compensation_reads_usd_after_each_level_endpoint() -> None:
    extracted = extract_annual_compensation_text(
        "The base salary range is 152,000 USD - 241,500 USD for Level 3, "
        "and 184,000 USD - 287,500 USD for Level 4."
    )

    assert extracted is not None
    assert evaluate_compensation(extracted, 160000).range_label == (
        "$152,000 - $287,500"
    )


def test_extract_annual_compensation_reads_multiple_annual_salary_ranges() -> None:
    extracted = extract_annual_compensation_text(
        "Annual Salary Range: IT Professional III $100,400 - $180,700 USD. "
        "Annual Salary Range: IT Professional II $83,600 - $150,500 USD."
    )

    assert extracted is not None
    assert evaluate_compensation(extracted, 160000).range_label == (
        "$83,600 - $180,700"
    )


def test_extract_annual_compensation_from_html_with_encoded_dash() -> None:
    description = (
        "<h3>Pay Transparency</h3>"
        "<h4>Base Compensation Range</h4>"
        "<p>$179,500 &ndash; $224,300 USD</p>"
    )

    extracted = extract_annual_compensation_text(description)
    result = evaluate_compensation(extracted, 160000)

    assert result.label == "Meets floor"
    assert result.range_label == "$179,500 - $224,300"
    assert result.min_usd == 179500
    assert result.max_usd == 224300


def test_extract_annual_compensation_handles_usd_before_each_amount() -> None:
    description = (
        "The expected annual pay range is "
        "USD $175,000 to USD $215,000 based on experience."
    )

    extracted = extract_annual_compensation_text(description)

    assert extracted is not None
    assert parse_salary_range_usd(extracted) == (175000, 215000)


def test_extract_annual_compensation_from_double_encoded_ats_html() -> None:
    description = (
        "&lt;div class=&quot;title&quot;&gt;Base Compensation Range&lt;/div&gt;"
        "&lt;div class=&quot;pay-range&quot;&gt;"
        "&lt;span&gt;$179,500&lt;/span&gt;"
        "&lt;span class=&quot;divider&quot;&gt;&amp;mdash;&lt;/span&gt;"
        "&lt;span&gt;$224,300 USD&lt;/span&gt;"
        "&lt;/div&gt;"
    )

    extracted = extract_annual_compensation_text(description)
    result = evaluate_compensation(extracted, 160000)

    assert result.label == "Meets floor"
    assert result.range_label == "$179,500 - $224,300"
    assert result.min_usd == 179500
    assert result.max_usd == 224300


def test_compensation_extractor_ignores_html_with_unrelated_large_numbers() -> None:
    description = (
        "<p>Operate a 100000-node platform used by customers in 25 countries.</p>"
    )

    assert extract_annual_compensation_text(description) is None


def test_compensation_extractor_ignores_unrelated_large_numbers() -> None:
    description = (
        "Operate a 100000-node platform used by customers in 25 countries."
    )

    assert extract_annual_compensation_text(description) is None
