"""Compare a posting's actual required work with evidence in the resume."""

from dataclasses import dataclass
from html import unescape
import re

from job_radar.candidate_profile import CandidateProfile
from job_radar.models import JobPosting
from job_radar.normalize import clean_text


@dataclass(frozen=True)
class ResumeMatchResult:
    label: str
    evidence: list[str]
    gaps: list[str]
    critical_gaps: list[str] | None = None
    requirements_reviewed: list[str] | None = None

    @property
    def has_critical_gap(self) -> bool:
        """A critical gap means the posting's central required work is unsupported."""

        return bool(self.critical_gaps)


def match_resume_to_posting(
    posting: JobPosting,
    candidate_profile: CandidateProfile | None,
    resume_text: str | None,
) -> ResumeMatchResult:
    if candidate_profile is None or not resume_text:
        return ResumeMatchResult(label="Unknown", evidence=[], gaps=[])

    normalized_resume_text = clean_text(resume_text).lower()
    description = clean_text(posting.description or "")
    if not _description_is_substantive(description):
        incomplete_gap = (
            "The collected posting did not include enough job-description detail "
            "to verify its required qualifications."
        )
        return ResumeMatchResult(
            label="Weak",
            evidence=[],
            gaps=[incomplete_gap],
            critical_gaps=[incomplete_gap],
            requirements_reviewed=[],
        )
    posting_text = _build_posting_text(posting)
    role_relevant_text = clean_text(
        " ".join(
            part
            for part in (
                posting.title,
                _build_role_relevant_text(posting.description or ""),
            )
            if part
        )
    ).lower()

    evidence = _find_resume_evidence(
        candidate_profile=candidate_profile,
        resume_text=normalized_resume_text,
        posting_text=role_relevant_text,
    )
    configured_gaps = _find_resume_gaps(
        candidate_profile=candidate_profile,
        posting_text=posting_text,
    )
    requirements = _extract_required_clauses(posting.description)
    critical_gaps = _find_critical_gaps(
        posting=posting,
        candidate_profile=candidate_profile,
        resume_text=normalized_resume_text,
        requirements=requirements,
        configured_gaps=configured_gaps,
        evidence=evidence,
    )
    gaps = _dedupe_preserving_order(configured_gaps + critical_gaps)
    role_alignment_confirmed = _role_alignment_is_confirmed(
        title=clean_text(posting.title).lower(),
        candidate_profile=candidate_profile,
    )

    return ResumeMatchResult(
        label=_classify_resume_match(
            evidence=evidence,
            gaps=gaps,
            critical_gaps=critical_gaps,
            role_alignment_confirmed=role_alignment_confirmed,
        ),
        evidence=evidence,
        gaps=gaps,
        critical_gaps=critical_gaps,
        requirements_reviewed=requirements,
    )


def _find_resume_evidence(
    candidate_profile: CandidateProfile,
    resume_text: str,
    posting_text: str,
) -> list[str]:
    evidence: list[str] = []

    for strength in candidate_profile.core_strengths + candidate_profile.credible_adjacent:
        normalized_strength = clean_text(strength).lower()

        if not normalized_strength:
            continue

        if _term_matches(normalized_strength, resume_text) and _term_matches(
            normalized_strength,
            posting_text,
        ):
            evidence.append(strength)

    return _dedupe_preserving_order(evidence)


def _find_resume_gaps(
    candidate_profile: CandidateProfile,
    posting_text: str,
) -> list[str]:
    gaps: list[str] = []

    for gap in candidate_profile.learning_or_gap:
        normalized_gap = clean_text(gap).lower()

        if not normalized_gap:
            continue

        if _should_report_resume_gap(
            normalized_gap=normalized_gap,
            posting_text=posting_text,
        ):
            gaps.append(gap)

    return _dedupe_preserving_order(gaps)


def _should_report_resume_gap(
    normalized_gap: str,
    posting_text: str,
) -> bool:
    return _term_matches(normalized_gap, posting_text)


def _classify_resume_match(
    evidence: list[str],
    gaps: list[str],
    critical_gaps: list[str] | None = None,
    role_alignment_confirmed: bool = True,
) -> str:
    if critical_gaps:
        return "Poor Fit"

    evidence_count = len(evidence)
    gap_count = len(gaps)

    if role_alignment_confirmed and evidence_count >= 4 and gap_count == 0:
        return "Very Strong"

    if role_alignment_confirmed and evidence_count >= 3 and gap_count <= 1:
        return "Strong"

    if evidence_count >= 1:
        return "Medium"

    return "Weak"


_REQUIREMENT_HEADINGS = (
    "required qualifications",
    "minimum qualifications",
    "must have",
    "what you need",
    "what we need",
    "we expect you to have",
    "you have",
    "you may be a good fit if",
    "you'll thrive in this role if",
    "you will thrive in this role if",
    "who you are",
    "what we're looking for",
    "what we are looking for",
    "the ideal candidate",
    "qualifications",
)


def _description_is_substantive(description: str) -> bool:
    """Reject records that contain no usable job-description text."""

    return bool(re.search(r"[a-zA-Z0-9]", description))
_STOP_HEADINGS = (
    "preferred qualifications",
    "desired qualifications",
    "nice to have",
    "bonus",
    "benefits",
    "compensation",
    "pay transparency",
    "about us",
    "equal opportunity",
)
_ROLE_SECTION_HEADINGS = (
    "about the role",
    "the role",
    "role overview",
    "responsibilities",
    "your responsibilities",
    "your responsibilities will include",
    "what you will do",
    "what you'll do",
    "what you’ll do",
    "the work",
    *_REQUIREMENT_HEADINGS,
)
_EXPLICIT_REQUIREMENT_MARKERS = (
    "required",
    "must have",
    "must possess",
    "minimum of",
    "at least",
    "years of experience",
    "experience with",
    "experience in",
    "proficiency in",
    "proficient in",
    "strong experience",
    "deep experience",
    "expertise in",
)
_TECHNOLOGY_REQUIREMENTS = {
    "Go": ("go", "golang"),
    "Rust": ("rust",),
    "Java": ("java",),
    "Fortran": ("fortran",),
    "MPI": ("mpi", "message passing interface"),
    "OpenMP": ("openmp",),
    "OpenACC": ("openacc",),
    "C++": ("c++",),
    "Terraform": ("terraform",),
    "Ansible": ("ansible",),
    "Kubernetes": ("kubernetes", "k8s"),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure",),
    "GCP": ("gcp", "google cloud"),
    "CUDA": ("cuda",),
    "machine learning": ("machine learning", "ml engineering"),
    "RTL verification": ("rtl", "systemverilog", "uvm"),
}
_DISCIPLINE_TERMS = {
    "civil, structural, or architectural engineering": (
        "civil engineer",
        "civil engineering",
        "structural engineer",
        "structural engineering",
        "architectural engineer",
        "architectural engineering",
        "building codes",
        "construction oversight",
        "facility design",
        "facilities design",
    ),
    "aerospace or spacecraft systems engineering": (
        "aerospace engineer",
        "aerospace engineering",
        "spacecraft",
        "space systems",
        "human landing system",
        "flight hardware",
        "mission assurance",
    ),
    "scientific-computing user support": (
        "scientific support",
        "scientific computing",
        "research computing support",
        "hpc application support",
        "application performance",
        "mpi",
        "openmp",
        "openacc",
        "fortran",
        "user training",
    ),
    "security engineering": (
        "security engineer",
        "infrastructure security",
        "application security",
        "cloud security",
        "security architecture",
        "threat detection",
        "vulnerability management",
    ),
    "software engineering": (
        "software engineer",
        "software developer",
        "backend engineer",
        "full stack",
        "full-stack",
        "application developer",
    ),
    "machine learning engineering": (
        "machine learning engineer",
        "ml engineer",
        "ai engineer",
        "research engineer",
        "data scientist",
    ),
    "electrical engineering": (
        "electrical engineer",
        "circuit design",
        "pcb design",
    ),
    "mechanical engineering": (
        "mechanical engineer",
        "mechanical design",
        "cad design",
    ),
    "product management": (
        "product manager",
        "product management",
    ),
    "supply chain": (
        "supply chain",
        "hardware sourcing",
        "strategic sourcing",
        "procurement",
    ),
    "tax and accounting": (
        "tax lead",
        "tax manager",
        "tax accounting",
        "tax compliance",
    ),
    "digital forensics": (
        "digital forensics",
        "forensic analyst",
        "forensic examiner",
    ),
    "retail grocery operations": (
        "produce department",
        "grocery bagger",
        "courtesy clerk",
        "food handling",
        "merchandising",
        "store associate",
    ),
}
_DISCIPLINES_REQUIRING_DESCRIPTION_CONFIRMATION = {
    # "HPC scientific support" can describe ordinary cluster operations or a
    # specialized scientific-application role. The requirements must establish
    # the specialized discipline before Junior treats it as a decisive mismatch.
    "scientific-computing user support",
}
_GENERIC_ROLE_WORDS = {
    "architect",
    "associate",
    "consultant",
    "director",
    "engineer",
    "engineering",
    "lead",
    "manager",
    "operations",
    "principal",
    "senior",
    "specialist",
    "staff",
    "system",
    "systems",
    "technology",
}
_ROLE_FAMILIES = {
    "infrastructure operations": (
        "infrastructure",
        "site reliability",
        "sre",
        "platform engineer",
        "hpc",
        "cluster",
        "linux",
        "datacenter",
        "data center",
        "systems administrator",
        "system administrator",
        "network engineer",
        "storage engineer",
        "cloud engineer",
    ),
    "hardware and platform validation": (
        "hardware validation",
        "platform validation",
        "system validation",
        "systems validation",
        "hardware integration",
        "system integration",
        "systems integration",
        "interoperability",
        "compliance testing",
    ),
}
_GAP_QUALIFIER_WORDS = {
    "heavy",
    "ownership",
    "production",
}
_AVOID_ROLE_FAMILIES = {
    "manager": (
        "manager",
        "group leader",
        "department leader",
        "director",
    ),
    "product management": (
        "product manager",
        "director of product",
        "head of product",
        "product management",
    ),
    "program management": (
        "program manager",
        "program management",
    ),
    "sales engineering": (
        "sales engineer",
        "solutions engineer",
        "sales engineering",
    ),
    "customer success": (
        "customer success",
        "client success",
    ),
    "frontend": (
        "frontend",
        "front end",
        "front-end",
    ),
    "full stack": (
        "full stack",
        "full-stack",
    ),
}


def _extract_required_clauses(description: str | None) -> list[str]:
    """Keep explicit must-have clauses and ignore preferred/benefit sections."""

    if not description:
        return []

    lines = _description_lines(description)
    required_section = False
    clauses: list[str] = []

    for line in lines:
        lowered = line.lower().rstrip(":")
        if any(
            lowered == heading or lowered.startswith(f"{heading}:")
            for heading in _STOP_HEADINGS
        ):
            required_section = False
            continue
        if any(
            lowered == heading or lowered.startswith(f"{heading}:")
            for heading in _REQUIREMENT_HEADINGS
        ):
            required_section = True
            continue

        for clause in re.split(r"[•●▪;]|(?<=[.!?])\s+", line):
            cleaned_clause = clean_text(clause).strip("-* ")
            lowered_clause = cleaned_clause.lower()
            if not cleaned_clause:
                continue
            if required_section or any(
                marker in lowered_clause for marker in _EXPLICIT_REQUIREMENT_MARKERS
            ):
                clauses.append(cleaned_clause)

    return _dedupe_preserving_order(clauses)


def _find_critical_gaps(
    *,
    posting: JobPosting,
    candidate_profile: CandidateProfile,
    resume_text: str,
    requirements: list[str],
    configured_gaps: list[str],
    evidence: list[str],
) -> list[str]:
    """Find unsupported central disciplines and explicit must-have technologies."""

    title = clean_text(posting.title).lower()
    required_text = " ".join(requirements).lower()
    target_text = " ".join(candidate_profile.target_roles).lower()
    profile_evidence = " ".join(
        candidate_profile.core_strengths + candidate_profile.credible_adjacent
    ).lower()
    supported_text = f"{resume_text} {profile_evidence} {target_text}"
    critical: list[str] = []

    avoided_role = _find_avoided_role_family(
        title=title,
        configured_avoid=candidate_profile.avoid,
    )
    if avoided_role is not None:
        critical.append(f"the role is in the excluded {avoided_role} job family")

    for discipline, markers in _DISCIPLINE_TERMS.items():
        central_to_title = any(_contains_phrase(title, marker) for marker in markers)
        central_to_requirements = sum(
            1 for marker in markers if _contains_phrase(required_text, marker)
        ) >= 2
        if discipline in _DISCIPLINES_REQUIRING_DESCRIPTION_CONFIRMATION:
            central_to_title = central_to_title and central_to_requirements
        supported = any(_contains_phrase(supported_text, marker) for marker in markers)
        if (central_to_title or central_to_requirements) and not supported:
            critical.append(f"central discipline requires {discipline} experience")

    for label, aliases in _TECHNOLOGY_REQUIREMENTS.items():
        explicitly_required = any(
            _technology_is_individually_required(clause, aliases)
            for clause in requirements
        )
        supported = any(_contains_phrase(supported_text, alias) for alias in aliases)
        if explicitly_required and not supported:
            critical.append(f"required {label} experience is not shown in the résumé")

    for gap in configured_gaps:
        normalized_gap = clean_text(gap).lower()
        if any(
            normalized_gap == discipline
            and f"central discipline requires {discipline} experience" in critical
            for discipline in _DISCIPLINE_TERMS
        ):
            continue
        if _configured_gap_is_central(normalized_gap, title) or any(
            _configured_gap_is_central(normalized_gap, clause.lower())
            and any(marker in clause.lower() for marker in _EXPLICIT_REQUIREMENT_MARKERS)
            for clause in requirements
        ):
            critical.append(f"required {gap} is a known profile gap")

    alignment_gap = _find_role_alignment_gap(
        title=title,
        candidate_profile=candidate_profile,
        evidence=evidence,
    )
    if alignment_gap is not None:
        critical.append(alignment_gap)

    return _dedupe_preserving_order(critical)


def _technology_is_individually_required(
    clause: str,
    aliases: tuple[str, ...],
) -> bool:
    """Do not turn one option in a technology list into a mandatory requirement."""

    lowered = clause.lower()
    if not any(_contains_phrase(lowered, alias) for alias in aliases):
        return False

    technologies_present = sum(
        1
        for technology_aliases in _TECHNOLOGY_REQUIREMENTS.values()
        if any(
            _contains_phrase(lowered, technology_alias)
            for technology_alias in technology_aliases
        )
    )
    offers_alternatives = any(
        marker in lowered
        for marker in (" one of ", " any of ", " or ", " such as ", " e.g.", " including ")
    )
    return not (technologies_present > 1 and offers_alternatives)


def _find_avoided_role_family(
    *,
    title: str,
    configured_avoid: list[str],
) -> str | None:
    normalized_avoid = {clean_text(value).lower() for value in configured_avoid}
    for avoided in normalized_avoid:
        # Generic management exclusions describe people-management roles. They
        # must not reject technical phrases such as vulnerability management.
        if avoided in {"manager", "management"}:
            continue
        if avoided and _contains_phrase(title, avoided):
            return avoided

    for family, title_markers in _AVOID_ROLE_FAMILIES.items():
        family_is_configured = family in normalized_avoid
        if family == "manager":
            family_is_configured = bool(
                normalized_avoid & {"manager", "management"}
            )
        if not family_is_configured:
            continue
        if any(_contains_phrase(title, marker) for marker in title_markers):
            return family
    return None


def _find_role_alignment_gap(
    *,
    title: str,
    candidate_profile: CandidateProfile,
    evidence: list[str],
) -> str | None:
    """Reject clearly unrelated titles without pretending uncertain titles are known."""

    if not candidate_profile.target_roles:
        return None

    if _role_alignment_is_confirmed(
        title=title,
        candidate_profile=candidate_profile,
    ):
        return None

    # Strong responsibility evidence can keep an unfamiliar title reviewable,
    # but classification caps it below Top Match until title alignment is clear.
    if len(evidence) >= 4:
        return None

    return "the job title and required work do not align with this profile's target work"


def _role_alignment_is_confirmed(
    *,
    title: str,
    candidate_profile: CandidateProfile,
) -> bool:
    """Compare actual work families instead of treating titles as synonyms."""

    if not candidate_profile.target_roles:
        return True

    # A skill can appear in work from an entirely different profession. Only
    # desired and explicitly adjacent roles may establish title alignment;
    # strengths still contribute responsibility evidence separately.
    profile_values = candidate_profile.target_roles + candidate_profile.credible_adjacent
    title_words = _meaningful_role_words(title)
    profile_words: set[str] = set()
    for value in profile_values:
        profile_words.update(_meaningful_role_words(clean_text(value).lower()))

    if title_words & profile_words:
        return True

    title_families = _role_families(title)
    profile_families: set[str] = set()
    for value in profile_values:
        profile_families.update(_role_families(clean_text(value).lower()))
    return bool(title_families & profile_families)


def _role_families(value: str) -> set[str]:
    return {
        family
        for family, markers in _ROLE_FAMILIES.items()
        if any(_contains_phrase(value, marker) for marker in markers)
    }


def _meaningful_role_words(value: str) -> set[str]:
    expanded = re.sub(r"\bsre\b", "site reliability", value)
    return {
        _role_stem(word)
        for word in re.findall(r"[a-z0-9+#]+", expanded)
        if len(word) >= 3 and word not in _GENERIC_ROLE_WORDS
    }


def _configured_gap_is_central(gap: str, text: str) -> bool:
    gap_words = {
        word
        for word in _meaningful_role_words(gap)
        if word not in _GAP_QUALIFIER_WORDS
    }
    text_words = _meaningful_role_words(text)
    return bool(gap_words) and gap_words.issubset(text_words)


def _role_stem(word: str) -> str:
    if word in {"engineer", "engineering"}:
        return "engineer"
    if word in {"developer", "development"}:
        return "develop"
    if word in {"manager", "management"}:
        return "manage"
    return word


def _build_role_relevant_text(posting_text: str) -> str:
    """Exclude employer marketing copy when the description has role sections."""

    lines = _description_lines(posting_text)
    if not lines:
        return posting_text

    role_lines: list[str] = []
    in_role_section = False
    found_role_heading = False

    for line in lines:
        lowered = line.lower().rstrip(":")
        if any(
            lowered == heading or lowered.startswith(f"{heading}:")
            for heading in _STOP_HEADINGS
        ):
            in_role_section = False
            continue
        if any(
            lowered == heading or lowered.startswith(f"{heading}:")
            for heading in _ROLE_SECTION_HEADINGS
        ):
            in_role_section = True
            found_role_heading = True
            continue
        if in_role_section:
            role_lines.append(line)

    if found_role_heading and role_lines:
        return clean_text(" ".join(role_lines)).lower()
    return posting_text


def _description_lines(description: str) -> list[str]:
    """Turn stored HTML or plain text into stable, section-aware lines."""

    decoded = unescape(description)
    decoded = re.sub(
        r"(?is)</?(?:h[1-6]|p|div|li|ul|ol|br|section|article)[^>]*>",
        "\n",
        decoded,
    )
    decoded = re.sub(r"(?is)<[^>]+>", " ", decoded)
    return [
        clean_text(line)
        for line in decoded.replace("\r", "\n").split("\n")
        if clean_text(line)
    ]


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def _term_matches(term: str, text: str) -> bool:
    if term in text:
        return True

    term_words = [word for word in term.split() if len(word) >= 3]

    if not term_words:
        return False

    return all(word in text for word in term_words)


def _build_posting_text(posting: JobPosting) -> str:
    parts = [
        posting.title,
        posting.location,
        posting.remote_status,
        posting.salary_text,
        posting.description,
    ]

    return clean_text(" ".join(part for part in parts if part)).lower()


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped_values: list[str] = []

    for value in values:
        if value not in deduped_values:
            deduped_values.append(value)

    return deduped_values
