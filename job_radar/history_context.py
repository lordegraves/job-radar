from job_radar.history_summary import HistorySummary


def build_history_context(summary: HistorySummary) -> list[str]:
    context: list[str] = []

    if summary.total_records == 0:
        return context

    pipeline_count = summary.history_type_counts.get("Pipeline", 0)
    reviewed_count = summary.history_type_counts.get("Reviewed", 0)

    context.append(
        f"Imported history: {summary.total_records} records "
        f"({pipeline_count} pipeline, {reviewed_count} reviewed)"
    )

    no_interview_count = summary.outcome_category_counts.get("No Interview", 0)
    interview_rejection_count = summary.outcome_category_counts.get(
        "Interview Rejection",
        0,
    )
    skipped_count = summary.outcome_category_counts.get("Skipped / Avoid", 0)

    if no_interview_count > 0:
        context.append(
            "Prior applications show technical match alone has not guaranteed "
            f"interviews ({no_interview_count} no-interview outcomes)"
        )

    if interview_rejection_count > 0:
        context.append(
            f"Prior interview rejections recorded: {interview_rejection_count}"
        )

    if skipped_count > 0:
        context.append(
            f"Prior reviewed roles skipped or avoided: {skipped_count}"
        )

    technical_no_interview_context = _build_technical_no_interview_context(summary)

    if technical_no_interview_context is not None:
        context.append(technical_no_interview_context)

    blocker_context = _build_blocker_context(summary)

    if blocker_context is not None:
        context.append(blocker_context)

    return context


def _build_technical_no_interview_context(
    summary: HistorySummary,
) -> str | None:
    no_interview_counts: list[str] = []

    for label in ["Very Strong", "Strong"]:
        key = f"{label} / No Interview"
        count = summary.technical_match_outcome_counts.get(key, 0)

        if count > 0:
            no_interview_counts.append(f"{key}: {count}")

    if not no_interview_counts:
        return None

    return "Strong technical matches with no interview: " + ", ".join(
        no_interview_counts
    )


def _build_blocker_context(summary: HistorySummary) -> str | None:
    useful_blockers = {
        blocker: count
        for blocker, count in summary.primary_blocker_counts.items()
        if blocker != "Unknown" and count > 0
    }

    if not useful_blockers:
        return None

    top_blockers = sorted(
        useful_blockers.items(),
        key=lambda item: (-item[1], item[0]),
    )[:3]

    return "Common prior blockers: " + ", ".join(
        f"{blocker}: {count}" for blocker, count in top_blockers
    )