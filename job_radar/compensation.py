"""Interpret advertised pay ranges and compare them with the candidate's floor."""

from dataclasses import dataclass
from html import unescape
import re


@dataclass(frozen=True)
class CompensationResult:
    label: str
    range_label: str
    min_usd: int | None = None
    max_usd: int | None = None


def evaluate_compensation(
    salary_text: str | None,
    compensation_floor_usd: int | None,
) -> CompensationResult:
    parsed_min, parsed_max = parse_salary_range_usd(salary_text)

    if parsed_min is None and parsed_max is None:
        return CompensationResult(
            label="Unknown",
            range_label="Unknown",
        )

    range_label = _format_range_label(parsed_min=parsed_min, parsed_max=parsed_max)

    if compensation_floor_usd is not None:
        if parsed_max is not None and parsed_max < compensation_floor_usd:
            return CompensationResult(
                label="Below floor",
                range_label=range_label,
                min_usd=parsed_min,
                max_usd=parsed_max,
            )

        if (
            parsed_min is not None
            and parsed_max is not None
            and parsed_min < compensation_floor_usd <= parsed_max
        ):
            return CompensationResult(
                label="Partial range meets floor",
                range_label=range_label,
                min_usd=parsed_min,
                max_usd=parsed_max,
            )

    return CompensationResult(
        label="Meets floor",
        range_label=range_label,
        min_usd=parsed_min,
        max_usd=parsed_max,
    )


def extract_annual_compensation_text(description: str | None) -> str | None:
    """Find an explicit annual pay statement when an ATS omits its salary field."""

    if not description:
        return None

    # ATS descriptions commonly contain HTML and encoded dash characters. Search
    # the human-readable text so the same pay wording works across collectors.
    readable_description = re.sub(r"<[^>]+>", " ", unescape(description))
    normalized = " ".join(readable_description.split())
    annual_marker = r"(?:annually|annual|per year|a year|/year|/yr|yearly)"
    currency = r"(?:USD\s*)?"
    money = rf"{currency}\$?\s*\d{{2,3}}(?:,\d{{3}})*(?:\.\d+)?\s*[kK]?"
    range_separator = r"(?:-|–|—|to|through)"
    trailing_currency = r"(?:\s*USD)?"
    patterns = (
        rf"(?:salary|pay|compensation)(?:\s+range)?[^.;:\n]{{0,30}}"
        rf"({money}\s*{range_separator}\s*{money}){trailing_currency}"
        rf"(?:\s*{annual_marker})?",
        rf"({money}\s*{range_separator}\s*{money}){trailing_currency}"
        rf"\s*{annual_marker}",
        rf"(?:salary|pay|compensation)(?:\s+is|\s+of|:)?\s*"
        rf"({money}){trailing_currency}\s*{annual_marker}",
    )

    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match is not None:
            return match.group(0)

    return None


def parse_salary_range_usd(salary_text: str | None) -> tuple[int | None, int | None]:
    if not salary_text:
        return None, None

    normalized = salary_text.replace(",", "")
    lowered = normalized.lower()

    if _looks_non_annual(lowered):
        return None, None

    numbers = _extract_salary_numbers(normalized)

    if not numbers:
        return None, None

    if len(numbers) == 1:
        return numbers[0], numbers[0]

    return min(numbers), max(numbers)


def _extract_salary_numbers(text: str) -> list[int]:
    values: list[int] = []

    for match in re.finditer(r"(?<!\d)(\$?\d+(?:\.\d+)?\s*[kK]?)(?!\d)", text):
        raw_value = match.group(1).strip()
        value = _parse_salary_number(raw_value)

        if value is None:
            continue

        if value < 10000:
            continue

        values.append(value)

    return values


def _parse_salary_number(raw_value: str) -> int | None:
    cleaned = raw_value.replace("$", "").strip()
    multiplier = 1

    if cleaned.lower().endswith("k"):
        multiplier = 1000
        cleaned = cleaned[:-1].strip()

    try:
        return int(float(cleaned) * multiplier)
    except ValueError:
        return None


def _looks_non_annual(text: str) -> bool:
    non_annual_markers = [
        "hourly",
        "/hr",
        "per hour",
        "an hour",
    ]

    return any(marker in text for marker in non_annual_markers)


def _format_range_label(parsed_min: int | None, parsed_max: int | None) -> str:
    if parsed_min is None and parsed_max is None:
        return "Unknown"

    if parsed_min is not None and parsed_max is not None and parsed_min == parsed_max:
        return _format_usd(parsed_min)

    if parsed_min is None:
        return f"Up to {_format_usd(parsed_max)}"

    if parsed_max is None:
        return f"From {_format_usd(parsed_min)}"

    return f"{_format_usd(parsed_min)} - {_format_usd(parsed_max)}"


def _format_usd(value: int | None) -> str:
    if value is None:
        return "Unknown"

    return f"${value:,.0f}"
