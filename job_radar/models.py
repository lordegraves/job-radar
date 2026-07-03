from dataclasses import dataclass
from hashlib import sha1


@dataclass(frozen=True)
class JobPosting:
    company_key: str
    company_name: str
    source_type: str
    source_url: str
    title: str
    location: str | None
    description: str | None
    source_job_id: str | None = None
    remote_status: str | None = None
    salary_text: str | None = None
    canonical_key: str | None = None
    content_hash: str | None = None

    @property
    def job_radar_id(self) -> str:
        identity_parts = [
            self.source_type,
            self.company_key,
            self.source_job_id
            or self.source_url
            or self.canonical_key
            or self.title
            or "",
            self.location or "",
        ]

        identity = "|".join(_normalize_identity_part(part) for part in identity_parts)
        digest = sha1(identity.encode("utf-8")).hexdigest()[:8]

        return f"jr-{_normalize_identity_part(self.company_key)}-{digest}"


def _normalize_identity_part(value: str | None) -> str:
    if value is None:
        return ""

    return "-".join(value.strip().lower().split())
