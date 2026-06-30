from job_radar.compensation import evaluate_compensation, parse_salary_range_usd


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


def test_evaluate_compensation_meets_floor_when_range_overlaps_floor() -> None:
    result = evaluate_compensation("USD $126,490.00/Yr. | USD $180,700.00/Yr.", 160000)

    assert result.label == "Meets floor"
    assert result.range_label == "$126,490 - $180,700"
    assert result.min_usd == 126490
    assert result.max_usd == 180700


def test_evaluate_compensation_unknown_without_salary_text() -> None:
    result = evaluate_compensation(None, 160000)

    assert result.label == "Unknown"
    assert result.range_label == "Unknown"
    assert result.min_usd is None
    assert result.max_usd is None