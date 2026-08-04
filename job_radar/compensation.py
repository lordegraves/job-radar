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
    # Some ATS feeds escape an already-escaped HTML fragment. Decode a small,
    # fixed number of times so visible salary ranges become ordinary text
    # without allowing unbounded processing.
    decoded_description = description
    for _ in range(3):
        next_description = unescape(decoded_description)
        if next_description == decoded_description:
            break
        decoded_description = next_description

    readable_description = re.sub(r"<[^>]+>", " ", decoded_description)
    normalized = " ".join(readable_description.split())
    annual_marker = r"(?:annually|annual|per year|a year|/year|/yr|yearly)"
    currency = r"(?:USD\s*)?"
    money = rf"{currency}\$?\s*\d{{2,3}}(?:,\d{{3}})*(?:\.\d+)?\s*[kK]?"
    # Multi-level postings sometimes put ``USD`` after each endpoint instead
    # of once after the whole range (for example, ``152,000 USD - 241,500
    # USD``). Treat either placement as the same annual currency evidence.
    range_money = rf"{money}(?:\s*USD)?"
    explicit_currency_money = (
        r"(?:USD\s*\$?\s*\d{2,3}(?:,\d{3})*(?:\.\d+)?\s*[kK]?|"
        r"\$\s*\d{2,3}(?:,\d{3})*(?:\.\d+)?\s*[kK]?(?:\s*USD)?|"
        r"\d{2,3}(?:,\d{3})*(?:\.\d+)?\s*[kK]?\s*USD)"
    )
    range_separator = r"(?:-|–|—|to|through)"
    trailing_currency = r"(?:\s*USD)?"
    patterns = (
        rf"({explicit_currency_money}\s*{range_separator}\s*"
        rf"{explicit_currency_money})\s+for\s+level\s+\d+",
        rf"{annual_marker}\s+(?:salary|pay|compensation)(?:\s+range)?\s*:\s*"
        rf"({range_money}\s*{range_separator}\s*{range_money}){trailing_currency}",
        rf"(?:salary|pay|compensation)(?:\s+range)?[^.;:\n]{{0,30}}"
        rf"({range_money}\s*{range_separator}\s*{range_money}){trailing_currency}"
        rf"(?:\s*{annual_marker})?",
        rf"({range_money}\s*{range_separator}\s*{range_money}){trailing_currency}"
        rf"\s*{annual_marker}",
        # Some ATS feeds put a labeled Salary Range heading in a separate HTML
        # node, leaving only the explicit USD range in the normalized text.
        rf"({range_money}\s*{range_separator}\s*{range_money})\s*USD\b",
        rf"(?:salary|pay|compensation)(?:\s+is|\s+of|:)?\s*"
        rf"({money}){trailing_currency}\s*{annual_marker}",
    )

    for pattern in patterns:
        matches = [
            match.group(0).strip()
            for match in re.finditer(pattern, normalized, flags=re.IGNORECASE)
        ]
        if matches:
            # A multi-level posting may advertise one range for each level.
            # Preserve every range matched by the same explicit pay pattern so
            # evaluation uses the complete advertised span instead of only the
            # first (usually lower-level) range.
            return "; ".join(dict.fromkeys(matches))

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
