from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreEvidence:
    points: int
    category: str
    source: str
    keyword: str

    @property
    def is_positive(self) -> bool:
        return self.points >= 0

    @property
    def signal_label(self) -> str:
        if self.source in {"title", "body"}:
            return f"{self.source}:{self.keyword}"

        return f"{self.category}:{self.keyword}"

    def to_legacy_reason(self) -> str:
        if self.category in {"positive_keyword", "location_allowed"}:
            points_label = f"+{self.points}"
        else:
            points_label = str(self.points)

        if self.source in {"title", "body"}:
            reason_label = f"{self.source}:{self.keyword}"
        else:
            reason_label = f"{self.category}:{self.keyword}"

        return f"{points_label} {reason_label}"
