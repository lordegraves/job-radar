import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HistorySummary:
    total_records: int
    history_type_counts: dict[str, int]
    outcome_category_counts: dict[str, int]
    primary_blocker_counts: dict[str, int]
    technical_match_outcome_counts: dict[str, int]


def build_history_summary(database_path: str | Path) -> HistorySummary:
    db_path = Path(database_path)

    with sqlite3.connect(db_path) as connection:
        return HistorySummary(
            total_records=_count_all_records(connection),
            history_type_counts=_count_grouped_values(connection, "history_type"),
            outcome_category_counts=_count_grouped_values(
                connection,
                "outcome_category",
            ),
            primary_blocker_counts=_count_grouped_values(
                connection,
                "primary_blocker",
            ),
            technical_match_outcome_counts=_count_technical_match_outcomes(
                connection,
            ),
        )


def format_history_summary(summary: HistorySummary) -> str:
    lines: list[str] = [
        "Job history summary",
        f"Total records: {summary.total_records}",
        "",
    ]

    _append_count_section(lines, "History types", summary.history_type_counts)
    _append_count_section(lines, "Outcome categories", summary.outcome_category_counts)
    _append_count_section(lines, "Top blockers", summary.primary_blocker_counts)
    _append_count_section(
        lines,
        "Technical match vs outcome",
        summary.technical_match_outcome_counts,
    )

    return "\n".join(lines).rstrip() + "\n"


def _count_all_records(connection: sqlite3.Connection) -> int:
    cursor = connection.execute("SELECT COUNT(*) FROM job_history")
    return int(cursor.fetchone()[0])


def _count_grouped_values(
    connection: sqlite3.Connection,
    column_name: str,
) -> dict[str, int]:
    cursor = connection.execute(
        f"""
        SELECT COALESCE(NULLIF({column_name}, ''), 'Unknown') AS label,
               COUNT(*) AS count
        FROM job_history
        GROUP BY label
        ORDER BY count DESC, label ASC
        """
    )

    return {str(row[0]): int(row[1]) for row in cursor.fetchall()}


def _count_technical_match_outcomes(
    connection: sqlite3.Connection,
) -> dict[str, int]:
    cursor = connection.execute(
        """
        SELECT
            COALESCE(NULLIF(technical_match, ''), 'Unknown') AS technical_match,
            COALESCE(NULLIF(outcome_category, ''), 'Unknown') AS outcome_category,
            COUNT(*) AS count
        FROM job_history
        GROUP BY technical_match, outcome_category
        ORDER BY count DESC, technical_match ASC, outcome_category ASC
        """
    )

    return {
        f"{str(row[0])} / {str(row[1])}": int(row[2])
        for row in cursor.fetchall()
    }


def _append_count_section(
    lines: list[str],
    heading: str,
    counts: dict[str, int],
) -> None:
    lines.append(f"{heading}:")

    if not counts:
        lines.append("- None")
        lines.append("")
        return

    for label, count in counts.items():
        lines.append(f"- {label}: {count}")

    lines.append("")