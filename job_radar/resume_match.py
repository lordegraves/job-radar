"""Compare a posting's actual required work with evidence in the resume."""

from dataclasses import dataclass
from datetime import date
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
    supported_requirements: list[str] | None = None

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

    # Preserve résumé line boundaries so one qualification cannot be "proven"
    # by combining unrelated words from separate bullets or positions.
    normalized_resume_text = unescape(resume_text).lower()
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
        posting_text=role_relevant_text,
    )
    requirements = _extract_required_clauses(posting.description)
    supported_requirements = _find_supported_required_qualifications(
        requirements=requirements,
        resume_text=normalized_resume_text,
    )
    evidence = _dedupe_preserving_order(
        evidence
        + [
            summary
            for requirement in supported_requirements
            if (summary := _summarize_supported_requirement(requirement))
        ]
    )
    qualification_gaps = _find_unsupported_required_qualifications(
        requirements=requirements,
        resume_text=normalized_resume_text,
    )
    critical_gaps = _find_critical_gaps(
        posting=posting,
        candidate_profile=candidate_profile,
        resume_text=normalized_resume_text,
        requirements=requirements,
        configured_gaps=configured_gaps,
        evidence=evidence,
    )
    central_platform_gaps = [
        gap
        for gap in qualification_gaps
        if gap.lower().startswith("no demonstrated ownership of a production ")
        or "at the scale required by the posting" in gap.lower()
        or (
            gap.lower().startswith("no clear résumé evidence of ")
            and " years of " in gap.lower()
        )
    ]
    if central_platform_gaps:
        # Explicit production ownership or at-scale depth is central required
        # work, not an adjacent skill that can safely remain review-only.
        critical_gaps = _dedupe_preserving_order(
            critical_gaps + central_platform_gaps
        )
    # Several independent mandatory capability gaps are collectively decisive
    # even when no single one names the role's central discipline. Reuse the
    # concise visible gaps so reports do not gain a duplicate explanation.
    decisive_required_gaps = (
        len(qualification_gaps) >= 3
        or (
            len(requirements) >= 2
            and len(qualification_gaps) >= 2
            and len(qualification_gaps) * 2 >= len(requirements)
        )
    )
    if decisive_required_gaps:
        critical_gaps = _dedupe_preserving_order(
            critical_gaps + qualification_gaps
        )
    gaps = _dedupe_preserving_order(
        configured_gaps + qualification_gaps + critical_gaps
    )
    role_alignment_confirmed = _role_alignment_is_confirmed(
        title=clean_text(posting.title).lower(),
        candidate_profile=candidate_profile,
    )
    specific_role_alignment_confirmed = _title_has_specific_target_role(
        title=clean_text(posting.title).lower(),
        candidate_profile=candidate_profile,
    )

    return ResumeMatchResult(
        label=_classify_resume_match(
            evidence=evidence,
            gaps=gaps,
            critical_gaps=critical_gaps,
            role_alignment_confirmed=role_alignment_confirmed,
            specific_role_alignment_confirmed=specific_role_alignment_confirmed,
            supported_requirement_count=len(supported_requirements),
            requirement_count=len(requirements),
        ),
        evidence=evidence,
        gaps=gaps,
        critical_gaps=critical_gaps,
        requirements_reviewed=requirements,
        supported_requirements=supported_requirements,
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
    # A configured multiword gap is one concept. Do not assemble it from
    # unrelated words scattered across a long description or employer boilerplate.
    return _contains_phrase(posting_text, normalized_gap)


def _classify_resume_match(
    evidence: list[str],
    gaps: list[str],
    critical_gaps: list[str] | None = None,
    role_alignment_confirmed: bool = True,
    specific_role_alignment_confirmed: bool = False,
    supported_requirement_count: int = 0,
    requirement_count: int = 0,
) -> str:
    if critical_gaps:
        return "Poor Fit"

    evidence_count = len(evidence)
    gap_count = len(gaps)
    majority_of_requirements_supported = bool(
        requirement_count >= 2
        and supported_requirement_count >= 2
        and supported_requirement_count * 2 >= requirement_count
    )

    if requirement_count == 0 and not specific_role_alignment_confirmed:
        # Shared tools and subject matter can make a posting worth reviewing,
        # but they cannot prove a strong fit when Junior extracted no mandatory
        # qualifications to compare with the resume.
        return "Medium" if evidence_count >= 1 else "Weak"

    if requirement_count == 1 and supported_requirement_count == 0:
        return "Medium" if evidence_count >= 1 else "Weak"

    if requirement_count >= 2 and supported_requirement_count < 2:
        # A broad résumé can contribute several adjacent strengths, but one
        # supported requirement is not enough evidence for a Strong verdict
        # when the employer supplied a real multi-item requirement section.
        return "Medium" if evidence_count >= 1 else "Weak"

    if (
        role_alignment_confirmed
        and majority_of_requirements_supported
        and evidence_count >= 1
        and gap_count <= 1
    ):
        return "Strong"

    if role_alignment_confirmed and evidence_count >= 4 and gap_count == 0:
        return "Very Strong"

    if role_alignment_confirmed and evidence_count >= 3 and gap_count <= 1:
        return "Strong"

    if evidence_count >= 1:
        return "Medium"

    return "Weak"


_REQUIREMENT_HEADINGS = (
    "required",
    "requirements",
    "required qualifications",
    "additional required qualifications",
    "basic qualifications",
    "other requirements",
    "required/minimum qualifications",
    "required minimum qualifications",
    "experience required",
    "education and experience required",
    "minimum qualifications",
    "must have",
    "what you need",
    "what we need",
    "what we need to see",
    "we expect you to have",
    "you have",
    "you may be a good fit if",
    "you may be a good fit if you",
    "what you bring",
    "what you'll bring",
    "what you will bring",
    "your background",
    "candidate profile",
    "technical skills",
    "knowledge and skills",
    "you'll thrive in this role if",
    "you will thrive in this role if",
    "who you are",
    "what we're looking for",
    "what we’re looking for",
    "what we are looking for",
    "about you",
    "about you (skills / qualifications)",
    "the ideal candidate",
    "qualifications",
)

_PREFERRED_HEADINGS = (
    "preferred",
    "preferred qualifications",
    "desired qualifications",
    "nice to have",
    "nice to haves",
    "bonus",
    "bonus points",
    "added bonus",
    "strong candidates may also",
    "it would be an added bonus if you have",
    "ways to stand out from the crowd",
    "additional qualifications",
)


def _description_is_substantive(description: str) -> bool:
    """Reject records that contain no usable job-description text."""

    return bool(re.search(r"[a-zA-Z0-9]", description))
_STOP_HEADINGS = (
    "preferred",
    "preferred qualifications",
    "desired qualifications",
    "nice to have",
    "bonus",
    "benefits",
    "compensation",
    "pay transparency",
    "about us",
    "equal opportunity",
    "working conditions",
)
_POST_QUALIFICATION_HEADINGS = (
    "benefits",
    "candidate privacy notice",
    "compensation",
    "equal opportunity employer",
    "equal opportunities statement",
    "friends of voleon",
    "logistics",
    "pay transparency",
    "salary range",
    "what success looks like",
    "what you'll receive",
    "what youâ€™ll receive",
    "why join us",
    "key employee benefits",
    "what we can offer you",
    "what we offer",
    "our offer",
    "impact/scope",
    "impact and scope",
    "complexity",
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
    "Python": ("python",),
    "Bash": ("bash", "shell scripting"),
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
    "InfiniBand": ("infiniband", "rdma"),
    "machine learning": ("machine learning", "ml engineering"),
    "RTL verification": ("rtl", "systemverilog", "uvm"),
}
_SCALE_CAPABILITY_ALIASES = {
    **_TECHNOLOGY_REQUIREMENTS,
    "Linux platform": ("linux platform", "linux infrastructure", "linux systems"),
    "network infrastructure": (
        "network infrastructure",
        "networking",
        "network platform",
    ),
    "storage platform": (
        "storage infrastructure",
        "storage platform",
        "distributed storage",
    ),
    "cloud infrastructure": ("cloud infrastructure", "cloud platform"),
    "marketing": (
        "marketing",
        "marketing science",
        "marketing analytics",
        "market strategy",
    ),
}
_SCALE_REQUIREMENT_MARKERS = (
    "at scale",
    "large-scale",
    "large scale",
    "production-scale",
    "production scale",
    "fleet-wide",
    "fleet wide",
)
_SCALE_RESUME_EVIDENCE_MARKERS = (
    "at scale",
    "large-scale",
    "large scale",
    "production",
    "owned",
    "ownership",
    "architected",
    "fleet-wide",
    "fleet wide",
    "cluster lifecycle",
    "platform lifecycle",
)
_DISCIPLINE_TERMS = {
    "civil, structural, or architectural engineering": (
        "civil engineer",
        "civil engineering",
        "civil site development",
        "structural engineer",
        "structural engineering",
        "structural design",
        "architectural engineer",
        "architectural engineering",
        "architectural programming",
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
        "software development",
        "kernel developer",
        "kernel-level software development",
        "linux kernel components",
        "backend engineer",
        "full stack",
        "full-stack",
        "application developer",
        "technical engineering experience with coding",
        "professional software engineering",
    ),
    "data engineering": (
        "data engineer",
        "data engineering",
        "distributed data processing",
        "etl orchestration",
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
    "coordinator",
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
_BROAD_ROLE_CONTEXT_WORDS = {
    "business",
    "data",
    "analytics",
    "digital",
    "enterprise",
    "information",
    "intelligence",
    "network",
    "platform",
    "product",
    "production",
    "software",
    "technical",
}
_OCCUPATION_NEUTRAL_TITLE_WORDS = {"technical"}
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
        "observability engineer",
        "storage engineer",
        "cloud engineer",
        "cloud platform",
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
        "solution engineer",
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
    "software engineering": (
        "software engineer",
        "software developer",
        "kernel developer",
        "linux kernel developer",
    ),
    "security engineering": (
        "security engineer",
        "security engineering",
        "cybersecurity engineer",
    ),
}


def _extract_required_clauses(description: str | None) -> list[str]:
    """Keep explicit must-have clauses and ignore preferred/benefit sections."""

    if not description:
        return []

    lines = _description_lines(description)
    has_requirement_heading = any(
        _matches_section_heading(line.lower().rstrip(":"), _REQUIREMENT_HEADINGS)
        for line in lines
    )
    required_section = False
    excluded_section = False
    clauses: list[str] = []

    for line in lines:
        lowered = line.lower().rstrip(":")
        if _matches_section_heading(lowered, _STOP_HEADINGS) or (
            _matches_section_heading(lowered, _PREFERRED_HEADINGS)
        ):
            required_section = False
            excluded_section = True
            continue
        if _matches_section_heading(lowered, _REQUIREMENT_HEADINGS):
            required_section = True
            excluded_section = False
            continue

        if _is_post_qualification_heading(lowered):
            required_section = False
            excluded_section = True
            continue

        for clause in re.split(r"[•●▪;]|(?<=[.!?])\s+", line):
            cleaned_clause = clean_text(clause).strip("-* ")
            lowered_clause = cleaned_clause.lower()
            if not cleaned_clause:
                continue
            if _looks_like_preferred_clause(cleaned_clause):
                continue
            if _looks_like_non_qualification_clause(cleaned_clause):
                continue
            should_include = required_section or (
                not has_requirement_heading
                and not excluded_section
                and _looks_like_explicit_requirement_clause(lowered_clause)
            )
            if should_include:
                clauses.extend(_expand_compound_requirement(cleaned_clause))

    return _dedupe_preserving_order(clauses)


def _expand_compound_requirement(requirement: str) -> list[str]:
    """Separate several mandatory experience durations joined by ATS text."""

    parts = re.split(r"\s+AND\s+", requirement)
    experience_parts = [
        re.sub(r"\s+OR\s+equivalent experience\??$", "", part).strip(" ,.;?")
        for part in parts
        if re.search(r"\b\d+\+?\s+years?\b", part, re.IGNORECASE)
    ]
    return experience_parts if len(experience_parts) >= 2 else [requirement]


def _extract_preferred_clauses(description: str | None) -> list[str]:
    """Keep preferred qualifications separate from mandatory requirements."""

    if not description:
        return []

    lines = _description_lines(description)
    preferred_section = False
    clauses: list[str] = []
    for line in lines:
        lowered = line.lower().rstrip(":")
        if _matches_section_heading(lowered, _PREFERRED_HEADINGS):
            preferred_section = True
            continue
        if _matches_section_heading(
            lowered, _REQUIREMENT_HEADINGS
        ) or _is_post_qualification_heading(lowered):
            preferred_section = False
            continue
        if not preferred_section:
            continue

        for clause in re.split(r"[â€¢â—â–ª;]|(?<=[.!?])\s+", line):
            cleaned_clause = clean_text(clause).strip("-* ")
            if cleaned_clause and not _looks_like_non_qualification_clause(
                cleaned_clause
            ):
                clauses.append(cleaned_clause)

    return _dedupe_preserving_order(clauses)


def _is_post_qualification_heading(value: str) -> bool:
    """Stop qualification parsing before outcomes, pay, benefits, or legal text."""

    lowered = value.lower().rstrip(":")
    if any(
        lowered == heading or lowered.startswith(f"{heading}:")
        for heading in _POST_QUALIFICATION_HEADINGS
    ):
        return True
    return (
        (lowered.startswith("what you") and "receive" in lowered)
        or "referral program" in lowered
        or "equal opportunity" in lowered
        or "privacy notice" in lowered
        or lowered.startswith("salary")
        or lowered.startswith("compensation")
        or lowered in {"benefits and perks", "perks and benefits", "our benefits"}
    )


def _matches_section_heading(value: str, headings: tuple[str, ...]) -> bool:
    """Recognize a section's function despite harmless wording differences."""

    lowered = clean_text(value).lower().rstrip(":")
    if lowered in headings:
        return True
    # Candidate-profile headings often finish an employer's stock phrase with
    # a pronoun, for example "You may be a good fit if you". Only extend short
    # heading-like lines; never turn a full requirement bullet into a heading.
    return bool(
        len(lowered.split()) <= 10
        and any(
            lowered.startswith(f"{heading} ")
            for heading in headings
            if len(heading.split()) >= 4
        )
    )


def _looks_like_non_qualification_clause(value: str) -> bool:
    """Exclude pay, benefits, legal, referral, and application boilerplate."""

    lowered = value.lower()
    sponsorship_notice = bool(
        re.search(
            r"\b(?:not eligible for|does not provide|will not provide)\b"
            r"[^.]{0,60}\b(?:visa|immigration) sponsorship\b",
            lowered,
        )
    )
    return (
        sponsorship_notice
        or "$" in value
        or "http://" in lowered
        or "https://" in lowered
        or any(
            marker in lowered
            for marker in (
                "equal opportunity",
                "without regard to race",
                "candidate privacy",
                "stock options",
                "flexible pto",
                "medical, dental",
                "home office stipend",
                "base pay for this position",
                "salary range",
                "referral bonus",
                "additional duties",
                "duties, tasks, and responsibilities as assigned",
                "candidate privacy",
                "employee privacy",
                "background check upon hire",
                "background check",
                "coding interviews",
                "401(k)",
                "parental leave",
                "what we can offer you",
                "key employee benefits",
                "participate in on-call",
                "participate in on call",
                "on-call as required",
                "on call as required",
                "collaborative, supportive, and innovative environment",
                "openai is an ai research",
                "we push the boundaries of the capabilities of ai systems",
                "interest in being engaged",
                "proof of employment eligibility",
                "employment eligibility as a condition of hire",
                "applications for this job will be accepted",
                "accommodations during the application process",
                "not eligible for visa sponsorship",
                "not eligible for immigration sponsorship",
                "immigration sponsorship is not available",
                "will not provide immigration sponsorship",
                "authorization to work in the united states",
                "minimum age",
                "for the role",
                "security screening requirements",
                "cloud background check",
                "these requirements include",
                "required for this role",
                "bias toward simplicity",
                "over-engineered observability stacks",
                "desire to be involved",
                "interest in being involved",
            )
        )
    )


def _looks_like_preferred_clause(value: str) -> bool:
    """Keep optional language out of mandatory résumé gaps."""

    lowered = value.lower()
    return bool(re.search(r"\bpreferred\b", lowered)) or bool(
        re.search(r"\ba plus\b", lowered)
    ) or any(
        marker in lowered
        for marker in (
            "nice to have",
            "nice-to-have",
            "is a plus",
            "are a plus",
            "would be a plus",
            "is preferred",
            "a strong plus",
            "(a plus)",
            "preferred but not required",
            "bonus if",
            "also welcome",
            "highly preferred",
            "useful differentiator",
            "useful differentiators",
        )
    )


def _looks_like_explicit_requirement_clause(value: str) -> bool:
    """Recognize must-have wording without matching incidental 'required' text."""

    lowered = clean_text(value).lower()
    if any(
        marker in lowered
        for marker in _EXPLICIT_REQUIREMENT_MARKERS
        if marker != "required"
    ):
        return True
    return bool(
        re.search(
            r"^(?:required\b|requirements?\s*:)|"
            r"\b(?:is|are)\s+required\b|"
            r"\brequired\s+(?:experience|qualification|qualifications|skill|skills)\b",
            lowered,
        )
    )


_DEGREE_DISCIPLINES = {
    "mechanical engineering": ("mechanical engineering",),
    "electrical engineering": ("electrical engineering",),
    "architecture": ("architecture", "architectural"),
    "civil engineering": ("civil engineering",),
    "computer science": ("computer science",),
}
_QUALIFICATION_EVIDENCE_STOP_WORDS = {
    "a",
    "an",
    "and",
    "ability",
    "applicable",
    "demonstrated",
    "experience",
    "familiarity",
    "for",
    "in",
    "including",
    "knowledge",
    "of",
    "or",
    "preferred",
    "proficiency",
    "required",
    "strong",
    "the",
    "to",
    "with",
}

_CAPABILITY_QUALIFIER_WORDS = {
    "direct",
    "hands",
    "mandatory",
    "practical",
    "proven",
    "role",
}


def _find_unsupported_required_qualifications(
    *,
    requirements: list[str],
    resume_text: str,
) -> list[str]:
    """Summarize the largest unsupported capabilities in mandatory requirements."""

    supported_text = resume_text.lower()
    resume_segment_tokens = [
        set(_qualification_evidence_tokens(segment))
        for segment in _resume_evidence_segments(supported_text)
    ]
    gaps: list[str] = []
    bounded_requirement_gaps = {
        requirement: gap
        for requirement in requirements
        if (
            gap := _skill_duration_requirement_gap(requirement, resume_text)
            or _scale_qualified_requirement_gap(requirement, resume_text)
        )
    }
    gaps.extend(bounded_requirement_gaps.values())
    for concept in _REQUIRED_GAP_CONCEPTS:
        matching_requirements = [
            requirement
            for markers in concept["requirement_patterns"]
            for requirement in requirements
            if requirement not in bounded_requirement_gaps
            if all(
                _contains_phrase(requirement.lower(), marker)
                for marker in markers
            )
        ]
        if not matching_requirements:
            continue
        if concept["gap"].startswith("No bachelor's degree") and all(
            "equivalent experience" in requirement.lower()
            for requirement in matching_requirements
        ):
            # Education is not a gap when the employer explicitly accepts the
            # candidate's experience as an alternative qualification route.
            continue
        resume_has_evidence = any(
            _contains_phrase(supported_text, marker)
            for marker in concept["resume_evidence"]
        )
        if not resume_has_evidence:
            gaps.append(concept["gap"])

    # Requirements represented by a larger capability gap are deliberately not
    # repeated sentence-by-sentence. For uncategorized requirements, preserve a
    # bounded concise summary only when the resume lacks meaningful evidence.
    for requirement in requirements:
        if len(gaps) >= 4:
            break
        if requirement in bounded_requirement_gaps:
            continue
        if _requirement_is_covered_by_gap_concept(requirement):
            continue
        if _qualification_has_resume_evidence(
            requirement,
            resume_text=resume_text,
            supported_text=supported_text,
            resume_segment_tokens=resume_segment_tokens,
        ):
            continue
        summary = _summarize_uncategorized_requirement(requirement)
        if summary:
            gaps.append(summary)

    return _dedupe_preserving_order(gaps)


def _find_supported_required_qualifications(
    *,
    requirements: list[str],
    resume_text: str,
) -> list[str]:
    """Return mandatory qualifications supported by coherent résumé evidence."""

    supported_text = resume_text.lower()
    resume_segment_tokens = [
        set(_qualification_evidence_tokens(segment))
        for segment in _resume_evidence_segments(supported_text)
    ]
    return [
        requirement
        for requirement in requirements
        if _qualification_has_resume_evidence(
            requirement,
            resume_text=resume_text,
            supported_text=supported_text,
            resume_segment_tokens=resume_segment_tokens,
        )
    ]


def _summarize_supported_requirement(requirement: str) -> str | None:
    """Turn supported requirements into short, résumé-grounded strengths."""

    lowered = requirement.lower()
    if "python" in lowered:
        return "Python scripting and automation"
    if re.search(r"\blinux\b", lowered):
        return "Linux infrastructure"
    if "communication" in lowered:
        return "technical communication"
    if (
        "network design" in lowered
        and "development" in lowered
        and "automation" in lowered
    ):
        return "network infrastructure and automation"
    if any(marker in lowered for marker in ("problem-solving", "problem solving")):
        return "production troubleshooting"
    if "relevant industry experience" in lowered:
        return "relevant industry experience"
    return None


_REQUIRED_GAP_CONCEPTS = (
    {
        "gap": (
            "No demonstrated Linux package-development and "
            "repository-management experience"
        ),
        "requirement_patterns": (
            ("packaging standards", "repository management"),
            ("package repositories", "software distribution infrastructure"),
        ),
        "resume_evidence": (
            "built deb packages",
            "built rpm packages",
            "linux package development",
            "package repository management",
            "managed package repositories",
            "software distribution infrastructure",
        ),
    },
    {
        "gap": (
            "No clear r\u00e9sum\u00e9 evidence of at least two years in a formal "
            "customer-facing deployment or technical-delivery role"
        ),
        "requirement_patterns": (
            ("customer-facing", "deployment"),
            ("customer facing", "deployment"),
            ("customer cto",),
            ("design partner engagement",),
        ),
        "resume_evidence": (
            "forward deployed engineer",
            "customer-facing deployment",
            "customer facing deployment",
            "deployment engineer",
            "technical delivery lead",
            "embedded with strategic customers",
        ),
    },
    {
        "gap": (
            "No demonstrated advanced network failure-model expertise across "
            "control and data planes, failure domains, and latency or loss"
        ),
        "requirement_patterns": (
            ("networking basics", "control plane", "data plane", "failure domains"),
            ("networks fail", "control plane", "data plane"),
        ),
        "resume_evidence": (
            "control plane",
            "data plane",
            "failure domain",
            "network failure model",
            "network fault model",
        ),
    },
    {
        "gap": "No demonstrated distributed-tracing or application-performance-monitoring experience",
        "requirement_patterns": (
            ("distributed tracing", "application performance monitoring"),
            ("distributed tracing", "apm"),
        ),
        "resume_evidence": (
            "distributed tracing",
            "application performance monitoring",
            "apm",
        ),
    },
    {
        "gap": "No demonstrated BGP, OSPF, EVPN, VXLAN, MLAG, or LACP network-design experience",
        "requirement_patterns": (
            ("high-speed ethernet", "bgp", "ospf"),
            ("ethernet networks", "evpn", "vxlan"),
        ),
        "resume_evidence": ("bgp", "ospf", "evpn", "vxlan", "mlag", "lacp"),
    },
    {
        "gap": "No demonstrated postmortem leadership experience",
        "requirement_patterns": (
            ("incident response", "postmortem"),
            ("incident management", "postmortem"),
        ),
        "resume_evidence": (
            "led postmortem",
            "postmortem leadership",
            "incident review leadership",
        ),
    },
    {
        "gap": "No large-scale endpoint fleet or modern MDM management experience",
        "requirement_patterns": (
            ("endpoint fleets", "mdm"),
            ("device fleet", "mdm"),
            ("modern mdm",),
        ),
        "resume_evidence": (
            "endpoint fleet",
            "device fleet",
            "mobile device management",
            "mdm platform",
            "jamf",
            "intune",
            "workspace one",
        ),
    },
    {
        "gap": "No endpoint configuration-as-code or device GitOps experience",
        "requirement_patterns": (
            ("endpoint configuration", "code"),
            ("device configuration", "gitops"),
            ("scripted deployments", "canary"),
        ),
        "resume_evidence": (
            "endpoint configuration as code",
            "device configuration as code",
            "endpoint gitops",
            "mdm gitops",
        ),
    },
    {
        "gap": "No demonstrated macOS endpoint-platform depth",
        "requirement_patterns": (
            ("macos internals",),
            ("macos", "windows internals"),
            ("launchd", "configuration profiles"),
        ),
        "resume_evidence": (
            "macos internals",
            "macos administration",
            "launchd",
            "configuration profiles",
            "tcc",
            "system extensions",
        ),
    },
    {
        "gap": "No fleet-scale zero-touch provisioning, patching, or software-distribution automation",
        "requirement_patterns": (
            ("zero touch", "patch"),
            ("device lifecycle automation",),
            ("patching", "software distribution"),
        ),
        "resume_evidence": (
            "zero touch enrollment",
            "zero touch provisioning",
            "endpoint patch automation",
            "software distribution automation",
            "device lifecycle automation",
        ),
    },
    {
        "gap": "No Civil, Structural, and Architectural (CSA) experience",
        "requirement_patterns": (
            ("civil", "structural", "architectural"),
            ("csa", "design"),
        ),
        "resume_evidence": (
            "civil engineering",
            "structural engineering",
            "architectural design",
            "csa design",
        ),
    },
    {
        "gap": "No data center CSA design experience",
        "requirement_patterns": (
            ("data center", "csa design"),
            ("hyperscale", "structural"),
            ("mission-critical", "architectural"),
        ),
        "resume_evidence": (
            "data center csa design",
            "datacenter csa design",
            "data center architectural design",
            "mission-critical facility design",
        ),
    },
    {
        "gap": "No experience as a lead technical authority",
        "requirement_patterns": (
            ("lead technical authority",),
            ("owner's engineer",),
            ("owners engineer",),
        ),
        "resume_evidence": (
            "technical authority",
            "owner's engineer",
            "owners engineer",
            "approved design deliverables",
        ),
    },
    {
        "gap": (
            "No proficiency with building-code standards such as IBC, IFC, "
            "ASCE 7, ACI 318, AISC, or FM Global"
        ),
        "requirement_patterns": (
            ("building codes",),
            ("building codes", "safety standards"),
            ("ibc", "ifc"),
        ),
        "resume_evidence": (
            "building codes",
            "ibc",
            "ifc",
            "asce 7",
            "aci 318",
            "aisc",
            "fm global",
        ),
    },
    {
        "gap": "No bachelor's degree in mechanical engineering, electrical engineering, or architecture",
        "requirement_patterns": (
            ("bs in", "mechanical engineering"),
            ("bachelor", "mechanical engineering"),
        ),
        "resume_evidence": (
            "bs in mechanical engineering",
            "b.s. mechanical engineering",
            "bachelor of mechanical engineering",
            "bs in electrical engineering",
            "b.s. electrical engineering",
            "bachelor of electrical engineering",
            "bachelor of architecture",
        ),
    },
    {
        "gap": "No experience managing design changes, RFIs, and construction documentation",
        "requirement_patterns": (("design change", "construction documentation"),),
        "resume_evidence": ("design change", "rfi", "construction documentation"),
    },
    {
        "gap": "No experience managing design execution with external design or construction firms",
        "requirement_patterns": (
            ("design execution", "external"),
            ("design execution", "construction firms"),
        ),
        "resume_evidence": ("design management", "owner's engineering", "construction program"),
    },
    {
        "gap": "No working knowledge of mechanical, electrical, and cooling systems",
        "requirement_patterns": (("mechanical", "electrical", "cooling"),),
        "resume_evidence": ("mechanical systems", "electrical systems", "cooling systems"),
    },
    {
        "gap": "No Kubernetes experience",
        "requirement_patterns": (("kubernetes",), ("k8s",)),
        "resume_evidence": ("kubernetes", "k8s"),
    },
    {
        "gap": "No demonstrated ownership of a production Kubernetes platform",
        "requirement_patterns": (
            ("kubernetes-based platforms", "production"),
            ("kubernetes platform", "production"),
        ),
        "resume_evidence": (
            "production kubernetes platform",
            "operated kubernetes in production",
            "production k8s platform",
            "kubernetes platform ownership",
        ),
    },
    {
        "gap": "No demonstrated InfiniBand network design or performance-tuning experience",
        "requirement_patterns": (
            ("infiniband", "configuration", "performance tuning"),
            ("infiniband networks", "designing"),
        ),
        "resume_evidence": (
            "designed infiniband",
            "infiniband network design",
            "infiniband performance tuning",
            "configured infiniband fabrics",
        ),
    },
    {
        "gap": "No demonstrated WAN design experience with MPLS, IPsec, GRE, or SD-WAN",
        "requirement_patterns": (
            ("wan technologies", "mpls", "ipsec"),
            ("wan infrastructure", "mpls"),
        ),
        "resume_evidence": (
            "mpls",
            "ipsec",
            "gre tunnel",
            "sd-wan",
            "wan design",
        ),
    },
    {
        "gap": "No experience defining service KPIs or error budgets",
        "requirement_patterns": (("kpi",), ("error budget",)),
        "resume_evidence": ("kpi", "key performance indicator", "error budget"),
    },
)


def _requirement_is_covered_by_gap_concept(requirement: str) -> bool:
    lowered = requirement.lower()
    return any(
        all(_contains_phrase(lowered, marker) for marker in markers)
        for concept in _REQUIRED_GAP_CONCEPTS
        for markers in concept["requirement_patterns"]
    )


def _summarize_uncategorized_requirement(requirement: str) -> str | None:
    """Avoid presenting employer prose as if it were Junior's analysis."""

    lowered = requirement.lower()
    # These broad professional behaviors are reasonably evidenced by ownership,
    # design, documentation, escalation, and cross-team work elsewhere in a resume.
    if any(
        marker in lowered
        for marker in (
            "communication with both technical and non-technical",
            "technical and non-technical audiences",
            "defend design decisions with incomplete information",
            "growth mindset",
            "passion for learning",
            "attention to detail",
            "high agency",
            "operational flexibility",
            "strategic problem-solver",
            "strategic problem solver",
            "security & reliability instincts",
            "security and reliability instincts",
            "remote-first operating excellence",
            "excitement about collaborating",
            "growth mindset",
            "comfortable owning complex systems end to end",
        )
    ):
        return None

    years_match = re.search(r"\b(\d+\+?)\s+years?\b", lowered)
    if years_match and any(
        marker in lowered
        for marker in ("software development", "software engineering", "coding")
    ):
        return (
            "No clear résumé evidence of "
            f"{years_match.group(1)} years of professional software development"
        )
    if "technical pre-sales" in lowered or "technical presales" in lowered:
        return "No clear résumé evidence of technical pre-sales experience"
    if "supply chain" in lowered and any(
        marker in lowered for marker in ("operational function", "operations")
    ):
        return (
            "No clear résumé evidence of supply-chain or logistics "
            "operations experience"
        )
    # Infrastructure that supports a data pipeline is not itself data
    # engineering. Treating the pipeline's workload as the candidate's required
    # discipline produced a false gap for Linux infrastructure positions.
    if (
        "infrastructure" in lowered
        and any(marker in lowered for marker in ("data pipeline", "analysis tool"))
    ):
        return None
    if "gpu & ai stack" in lowered or "gpu and ai stack" in lowered:
        return "No demonstrated GPU software-stack experience"
    if "centralized logging" in lowered and any(
        marker in lowered
        for marker in ("elastic stack", "splunk", "cloudwatch", "elk")
    ):
        return "No demonstrated centralized-logging platform experience"
    if any(
        marker in lowered
        for marker in ("data engineering", "data pipelines", "data platform")
    ):
        return "No clear résumé evidence of data-engineering experience"

    # Many employers lead a requirement with a concise capability label, then
    # explain it after a colon. The label is the useful gap summary; repeating
    # the full employer sentence made the GUI noisy and misleading.
    label, separator, _detail = requirement.partition(":")
    cleaned_label = clean_text(label).strip("-* ")
    if (
        separator
        and 2 <= len(cleaned_label.split()) <= 10
        and len(cleaned_label) <= 80
        and not _looks_like_non_qualification_clause(cleaned_label)
    ):
        return f"No clear résumé evidence of {cleaned_label}"

    # For ordinary bullets, separate the core qualification from an employer's
    # explanatory aside. Do not truncate at an arbitrary word count: that hid
    # the meaning of otherwise useful gaps in the GUI.
    cleaned = clean_text(requirement).strip("-* ")
    cleaned = re.sub(
        r"^(?:you (?:have|bring)|have|must have|demonstrated|proven|strong)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    for separator in (" — ", " – ", ";"):
        core, found, _detail = cleaned.partition(separator)
        if found and len(core.split()) >= 3:
            cleaned = core.strip(" ,;:.-")
            break

    if len(cleaned.split()) < 3:
        return None
    return f"No clear résumé evidence of {cleaned[0].lower() + cleaned[1:]}"


def _find_unsupported_preferred_qualifications(
    *,
    requirements: list[str],
    resume_text: str,
) -> list[str]:
    """Report every unsupported optional qualification separately."""

    supported_text = resume_text.lower()
    return [
        f"No resume evidence found for preferred qualification: {requirement}"
        for requirement in requirements
        if not _qualification_has_resume_evidence(
            requirement,
            resume_text=resume_text,
            supported_text=supported_text,
        )
    ]


def _qualification_has_resume_evidence(
    qualification: str,
    *,
    resume_text: str,
    supported_text: str,
    resume_segment_tokens: list[set[str]] | None = None,
) -> bool:
    """Require meaningful evidence coverage, not one generic matching word."""

    lowered = qualification.lower()
    duration_support = _skill_duration_requirement_is_supported(
        lowered,
        resume_text=resume_text,
    )
    if duration_support is not None:
        return duration_support
    scale_support = _scale_qualified_requirement_is_supported(
        lowered,
        resume_text=resume_text,
    )
    if scale_support is not None:
        return scale_support
    # A degree-or-equivalent clause is not a standalone education gap. The
    # posting's experience requirements are evaluated separately against the
    # résumé; treating this clause as degree-only rejected experienced people.
    if "equivalent experience" in lowered and any(
        marker in lowered for marker in ("bachelor", "b.s.", "bs in", "degree in")
    ):
        return True
    if any(
        marker in lowered
        for marker in ("proficiency in english", "proficient in english", "english proficiency")
    ) and len(re.findall(r"\b[a-z]{3,}\b", supported_text)) >= 40:
        # A substantive English-language résumé is direct written-language evidence.
        return True
    if _broad_experience_duration_is_supported(lowered, supported_text):
        return True
    if _compound_operational_design_is_supported(lowered, supported_text):
        return True
    if any(marker in lowered for marker in ("bachelor", "undergraduate", "degree")) and (
        ("equivalent" in lowered and "experience" in lowered)
        or "comparable training" in lowered
    ):
        return True
    degree_required = "equivalent experience" not in lowered and any(
        marker in lowered for marker in ("bachelor", "b.s.", "bs in", "degree in")
    )
    if degree_required:
        required_disciplines = [
            label
            for label, aliases in _DEGREE_DISCIPLINES.items()
            if any(_contains_phrase(lowered, alias) for alias in aliases)
        ]
        if required_disciplines:
            return _resume_shows_required_degree(resume_text, required_disciplines)

    qualification_tokens = _qualification_evidence_tokens(lowered)
    if not qualification_tokens:
        return False
    if _bounded_capability_evidence_supports(
        lowered,
        supported_text=supported_text,
    ):
        return True
    if _direct_named_capability_is_supported(
        lowered,
        supported_text=supported_text,
    ):
        return True
    # Evidence must describe one coherent piece of work. Combining unrelated
    # words from distant résumé bullets made specialized qualifications appear
    # supported merely because the candidate had a broad technical career.
    required_matches = max(1, (len(qualification_tokens) * 2 + 2) // 3)
    segment_tokens = resume_segment_tokens or [
        set(_qualification_evidence_tokens(segment))
        for segment in _resume_evidence_segments(supported_text)
    ]
    if any(
        marker in lowered
        for marker in ("any of the following", "such as", "including")
    ):
        # An explicitly alternative tool list is satisfied by one named option.
        option_tokens = {
            alias.lower()
            for aliases in _TECHNOLOGY_REQUIREMENTS.values()
            for alias in aliases
        }
        required_options = set(qualification_tokens) & option_tokens
        if required_options and any(
            required_options & evidence_tokens
            for evidence_tokens in segment_tokens
        ):
            return True
    if _alternative_capability_is_supported(
        lowered,
        resume_segments=_resume_evidence_segments(supported_text),
    ):
        return True
    return any(
        sum(token in evidence_tokens for token in qualification_tokens)
        >= required_matches
        for evidence_tokens in segment_tokens
    )


def _direct_named_capability_is_supported(
    requirement: str,
    *,
    supported_text: str,
) -> bool:
    """Recognize a concrete named capability without requiring hiring-language filler.

    Employers commonly wrap a concise skill in wording such as "hands-on
    experience in Power BI (mandatory)." The résumé must contain the named
    capability itself, but it does not need to repeat words such as "hands-on"
    or "mandatory."
    """

    match = re.search(
        r"(?:experience|proficiency|knowledge|expertise)\s+"
        r"(?:with|in|of)\s+(.+)$",
        requirement,
    )
    if match is None:
        return False

    capability = re.sub(r"\([^)]*\)", " ", match.group(1))
    capability = re.split(
        r"[.;]|\b(?:and the ability to|while|who|that)\b",
        capability,
        maxsplit=1,
    )[0]
    tokens = [
        token
        for token in _qualification_evidence_tokens(capability)
        if token not in _CAPABILITY_QUALIFIER_WORDS
    ]
    if not tokens or len(tokens) > 5:
        return False

    phrase = " ".join(tokens)
    return len(tokens) >= 2 and _contains_phrase(supported_text, phrase)


def _scale_qualified_requirement_is_supported(
    requirement: str,
    *,
    resume_text: str,
) -> bool | None:
    """Preserve explicit scale requirements without tightening ordinary skills."""

    if not any(
        _contains_phrase(requirement, marker)
        for marker in _SCALE_REQUIREMENT_MARKERS
    ):
        return None

    matching_aliases = [
        aliases
        for aliases in _SCALE_CAPABILITY_ALIASES.values()
        if any(_contains_phrase(requirement, alias) for alias in aliases)
    ]
    if not matching_aliases:
        return None

    return any(
        any(_contains_phrase(segment, alias) for alias in aliases)
        and any(
            _contains_phrase(segment, marker)
            for marker in _SCALE_RESUME_EVIDENCE_MARKERS
        )
        for aliases in matching_aliases
        for segment in _resume_evidence_segments(resume_text)
    )


def _scale_qualified_requirement_gap(
    requirement: str,
    resume_text: str,
) -> str | None:
    """Summarize an unsupported scale requirement without copying employer prose."""

    support = _scale_qualified_requirement_is_supported(
        requirement.lower(),
        resume_text=resume_text,
    )
    if support is not False:
        return None

    lowered = requirement.lower()
    label = next(
        (
            capability
            for capability, aliases in _SCALE_CAPABILITY_ALIASES.items()
            if any(_contains_phrase(lowered, alias) for alias in aliases)
        ),
        "technical platform",
    )
    return f"No demonstrated {label} experience at the scale required by the posting"


_RESUME_DATE_TOKEN = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|sept(?:ember)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?)\.?\s+\d{4}|\d{1,2}/\d{4}|\d{4}"
)
_RESUME_DATE_RANGE = re.compile(
    rf"(?P<start>{_RESUME_DATE_TOKEN})\s*"
    rf"(?:-|\u2013|\u2014|to)\s*"
    rf"(?P<end>{_RESUME_DATE_TOKEN}|present|current)",
    re.IGNORECASE,
)
_MONTH_NUMBERS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_RESUME_EMPLOYMENT_STOP_HEADINGS = {
    "certifications",
    "education",
    "projects",
    "skills",
    "technical skills",
}


def _skill_duration_requirement_is_supported(
    requirement: str,
    *,
    resume_text: str,
) -> bool | None:
    """Compare years only when a duration is tied to a named capability."""

    ranged_duration = re.search(
        r"\b(\d+)\s*[-\u2013\u2014]\s*\d+\s+years?\b",
        requirement,
    )
    duration = ranged_duration or re.search(
        r"\b(\d+)\+?\s+years?\b",
        requirement,
    )
    if duration is None:
        return None

    matching_capabilities = [
        (label, aliases)
        for label, aliases in _SCALE_CAPABILITY_ALIASES.items()
        if any(_contains_phrase(requirement, alias) for alias in aliases)
    ]
    if (
        not matching_capabilities
        and ranged_duration is not None
        and "years of experience" in requirement
    ):
        inferred_aliases = _duration_capability_aliases(requirement)
        if inferred_aliases:
            matching_capabilities = [("named capability", inferred_aliases)]
    if not matching_capabilities:
        return None

    required_months = int(duration.group(1)) * 12
    return any(
        _resume_capability_months(resume_text, aliases) >= required_months
        for _label, aliases in matching_capabilities
    )


def _skill_duration_requirement_gap(
    requirement: str,
    resume_text: str,
) -> str | None:
    """Explain a missing skill duration without claiming the skill is absent."""

    support = _skill_duration_requirement_is_supported(
        requirement.lower(),
        resume_text=resume_text,
    )
    if support is not False:
        return None

    ranged_years = re.search(
        r"\b(\d+)\s*[-\u2013\u2014]\s*\d+\s+years?\b",
        requirement.lower(),
    )
    years = ranged_years or re.search(
        r"\b(\d+)\+?\s+years?\b",
        requirement.lower(),
    )
    labels = [
        label
        for label, aliases in _SCALE_CAPABILITY_ALIASES.items()
        if any(_contains_phrase(requirement.lower(), alias) for alias in aliases)
    ]
    if (
        not labels
        and ranged_years is not None
        and "years of experience" in requirement.lower()
    ):
        inferred_aliases = _duration_capability_aliases(requirement.lower())
        if inferred_aliases:
            labels = [inferred_aliases[0]]
    if years is None or not labels:
        return None
    capability = " or ".join(labels)
    return (
        f"No clear résumé evidence of {years.group(1)} years of "
        f"{capability} experience"
    )


def _duration_capability_aliases(requirement: str) -> tuple[str, ...]:
    """Extract bounded capability alternatives from an ordinary duration clause."""

    match = re.search(
        r"\byears?\b[^.;]{0,50}?\b(?:in|with|of)\s+([^.;]+)",
        requirement,
    )
    if match is None:
        return ()

    capability_text = re.split(
        r"\b(?:including|who|that|while|and the ability to)\b",
        match.group(1),
        maxsplit=1,
    )[0]
    aliases: list[str] = []
    for option in re.split(r"\s*(?:/|\bor\b)\s*", capability_text):
        tokens = [
            token
            for token in _qualification_evidence_tokens(option)
            if token not in _CAPABILITY_QUALIFIER_WORDS
        ]
        if 1 <= len(tokens) <= 4:
            alias = " ".join(tokens)
            if alias not in aliases:
                aliases.append(alias)

    # These are grammatical forms of the same occupation family, not different
    # capabilities. This lets a dated Analyst role support an Analytics-duration
    # requirement without making an unrelated data role equivalent.
    expanded = list(aliases)
    if any(
        alias in {"analytic", "analytics", "analysis", "analyst"}
        for alias in aliases
    ):
        for alias in ("analytic", "analytics", "analysis", "analyst"):
            if alias not in expanded:
                expanded.append(alias)
    return tuple(expanded)


def _resume_capability_months(
    resume_text: str,
    aliases: tuple[str, ...],
) -> int:
    """Return supported months from explicit claims or dated employment blocks."""

    explicit_years = [
        int(match.group(1))
        for segment in _resume_evidence_segments(resume_text)
        if any(_contains_phrase(segment, alias) for alias in aliases)
        for match in re.finditer(r"\b(\d+)\+?\s+years?\b", segment)
    ]
    explicit_months = max(explicit_years, default=0) * 12

    dated_intervals: list[tuple[int, int]] = []
    for start, end, block in _dated_resume_blocks(resume_text):
        if any(_contains_phrase(block, alias) for alias in aliases):
            dated_intervals.append((start, end))
    return max(explicit_months, _merged_interval_months(dated_intervals))


def _dated_resume_blocks(resume_text: str) -> list[tuple[int, int, str]]:
    """Associate résumé bullets with the dated role immediately above them."""

    blocks: list[tuple[int, int, list[str]]] = []
    current: tuple[int, int, list[str]] | None = None
    for raw_line in resume_text.splitlines():
        line = clean_text(raw_line)
        if current is not None and line.lower().rstrip(":") in _RESUME_EMPLOYMENT_STOP_HEADINGS:
            blocks.append(current)
            current = None
            continue
        date_match = _RESUME_DATE_RANGE.search(line)
        if date_match:
            if current is not None:
                blocks.append(current)
            start = _resume_month_index(date_match.group("start"), is_end=False)
            end = _resume_month_index(date_match.group("end"), is_end=True)
            current = (start, end, [line])
        elif current is not None:
            current[2].append(line)
    if current is not None:
        blocks.append(current)
    return [
        (start, end, " ".join(lines).lower())
        for start, end, lines in blocks
        if end >= start
    ]


def _resume_month_index(value: str, *, is_end: bool) -> int:
    """Convert common résumé dates into a comparable month number."""

    normalized = value.lower().strip().rstrip(".")
    if normalized in {"present", "current"}:
        today = date.today()
        return today.year * 12 + today.month - 1
    slash_match = re.fullmatch(r"(\d{1,2})/(\d{4})", normalized)
    if slash_match:
        month, year = (int(part) for part in slash_match.groups())
        return year * 12 + month - 1
    year_match = re.fullmatch(r"\d{4}", normalized)
    if year_match:
        year = int(normalized)
        month = 12 if is_end else 1
        return year * 12 + month - 1
    month_match = re.match(r"([a-z]+)\.?\s+(\d{4})", normalized)
    if month_match is None:
        return 0
    month = _MONTH_NUMBERS[month_match.group(1)[:3]]
    year = int(month_match.group(2))
    return year * 12 + month - 1


def _merged_interval_months(intervals: list[tuple[int, int]]) -> int:
    """Add dated skill periods without counting overlapping jobs twice."""

    if not intervals:
        return 0
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return sum(end - start + 1 for start, end in merged)


_BOUNDED_CAPABILITY_EVIDENCE = (
    {
        "requirement": ("project management", "project"),
        "evidence": (
            "project management",
            "program management",
            "managed projects",
            "led projects",
        ),
    },
    {
        "requirement": ("budget management", "budget"),
        "evidence": (
            "budgeting",
            "budget management",
            "financial planning",
            "resource allocation",
        ),
    },
    {
        "requirement": ("interpersonal skills",),
        "evidence": (
            "cross-functional collaboration",
            "stakeholder communication",
            "stakeholder management",
            "team collaboration",
        ),
        "standalone": True,
    },
    {
        "requirement": (
            "work as part of a team",
            "teamwork",
            "team collaboration",
        ),
        "evidence": (
            "cross-functional collaboration",
            "team collaboration",
            "led teams",
            "leading teams",
        ),
        "standalone": True,
    },
    {
        "requirement": (
            "multiple levels of the organization",
            "technical and non-technical audiences",
            "executive stakeholders",
        ),
        "evidence": (
            "executive leadership",
            "senior management team",
            "stakeholder communication",
            "cross-functional collaboration",
        ),
        "standalone": True,
    },
    {
        "requirement": ("large, complex datasets", "large complex datasets"),
        "evidence": (
            "large dataset",
            "complex dataset",
            "data sources",
            "skus",
            "million",
            "billion",
        ),
        "standalone": True,
    },
    {
        "requirement": (
            "marketing principles",
            "marketing practices",
            "marketing tactics",
        ),
        "evidence": (
            "marketing analytics",
            "marketing attribution",
            "campaign roi",
            "market strategy",
            "marketing strategy",
            "marketing campaign",
        ),
        "standalone": True,
    },
    {
        "requirement": ("linux",),
        "evidence": ("linux",),
        "standalone": True,
    },
    {
        "requirement": ("python",),
        "evidence": ("python",),
        "standalone": True,
    },
    {
        "requirement": ("bash", "shell scripting"),
        "evidence": ("bash", "shell scripting", "shell automation"),
        "standalone": True,
    },
    {
        "requirement": ("automation", "scripting"),
        "evidence": ("automation", "scripting", "python", "powershell", "bash"),
        "standalone": True,
    },
    {
        "requirement": ("networking", "network expertise", "network fundamentals"),
        "evidence": ("networking", "network infrastructure", "network operations"),
        "standalone": True,
    },
    {
        "requirement": ("troubleshoot", "debugging"),
        "evidence": (
            "troubleshoot",
            "troubleshooting",
            "debug",
            "root cause",
            "root-cause",
            "failure analysis",
        ),
        "standalone": True,
    },
    {
        "requirement": ("hardware and software", "hardware, software"),
        "evidence": (
            "hardware/software boundary",
            "hardware and software",
            "hardware-software",
            "hardware–os–platform boundary",
            "hardware, os, platform",
            "hardware, firmware, linux operating system, and container",
        ),
        "standalone": True,
    },
    {
        "requirement": ("distributed systems", "distributed system"),
        "evidence": ("distributed systems", "distributed compute"),
        "standalone": True,
    },
    {
        "requirement": (
            "failure modes",
            "high-availability systems",
            "high availability systems",
            "reliability",
        ),
        "evidence": (
            "reliability engineering",
            "high availability",
            "failure analysis",
            "incident response",
        ),
        "standalone": True,
    },
    {
        "requirement": (
            "incident response",
            "root-cause analysis",
            "root cause analysis",
            "corrective actions",
        ),
        "evidence": (
            "incident response",
            "root-cause analysis",
            "root cause analysis",
            "corrective action",
            "failure analysis",
            "problem management",
        ),
        "standalone": True,
    },
    {
        "requirement": ("containerized production", "production containers"),
        "evidence": (
            "production kubernetes",
            "production containers",
            "containerized production",
        ),
    },
    {
        "requirement": ("sli", "slos", "slo", "error budget"),
        "evidence": ("sli", "slos", "slo", "error budget"),
    },
    {
        "requirement": ("system performance", "performance optimization"),
        "evidence": ("system performance", "performance optimization", "performance"),
        "standalone": True,
    },
    {
        "requirement": (
            "problem-solving",
            "problem solving",
            "analytical",
            "analytic",
            "critical thinking",
        ),
        "evidence": (
            "troubleshoot",
            "troubleshooting",
            "root cause",
            "root-cause",
            "failure analysis",
            "problem solving",
            "analysis",
            "analytical",
            "recommended",
            "recommendations",
            "strategic insights",
        ),
        "standalone": True,
    },
    {
        "requirement": ("written communication", "written communications"),
        "evidence": (
            "engineering documentation",
            "operational runbooks",
            "implementation blueprint",
            "technical and non-technical",
            "written communication",
        ),
        "standalone": True,
    },
    {
        "requirement": (
            "modern infrastructure tooling",
            "infrastructure-as-code",
            "infrastructure as code",
        ),
        "evidence": (
            "infrastructure as code",
            "terraform",
            "ansible",
            "ci/cd",
            "jenkins",
            "kubernetes",
        ),
        "standalone": True,
    },
    {
        "requirement": ("modern server architecture", "server architecture"),
        "evidence": (
            "rack-scale",
            "bare-metal",
            "hardware management",
            "hardware integration",
            "server systems",
        ),
        "standalone": True,
    },
    {
        "requirement": ("computer networks", "network knowledge"),
        "evidence": (
            "networking",
            "network infrastructure",
            "cluster networking",
            "tcp/ip",
            "vlans",
        ),
        "standalone": True,
    },
    {
        "requirement": ("tcp/ip network protocol", "tcp/ip"),
        "evidence": ("tcp/ip",),
        "standalone": True,
    },
    {
        "requirement": ("configuration management platform",),
        "evidence": ("ansible", "puppet", "chef", "cfengine"),
        "standalone": True,
    },
    {
        "requirement": (
            "infrastructure configuration management tools",
            "automating storage deployments",
        ),
        "evidence": ("ansible", "terraform", "puppet", "chef", "cfengine"),
        "standalone": True,
    },
    {
        "requirement": ("hpc", "high-performance computing"),
        "evidence": ("hpc", "high-performance computing", "slurm"),
        "standalone": True,
    },
    {
        "requirement": (
            "batch scheduling system",
            "batch scheduler",
            "scheduling system",
            "slurm",
            "kueue",
            "armada",
            "volcano",
        ),
        "evidence": (
            "slurm",
            "batch scheduler",
            "batch scheduling",
            "workload scheduler",
            "job scheduler",
        ),
        "standalone": True,
    },
    {
        "requirement": (
            "prometheus",
            "grafana",
            "modern monitoring platforms",
            "monitoring platforms",
        ),
        "evidence": ("prometheus", "grafana", "zabbix", "monitoring"),
        "standalone": True,
    },
    {
        "requirement": ("infiniband", "rdma", "roce"),
        "evidence": ("infiniband", "rdma", "roce"),
        "standalone": True,
    },
    {
        "requirement": ("cross-layer", "system-level troubleshooting"),
        "evidence": (
            "cross-layer failures",
            "hardware–os–platform boundary",
            "hardware-level systems debugging",
            "root cause analysis",
        ),
        "standalone": True,
    },
    {
        "requirement": (
            "communication & collaboration",
            "effective communication",
            "technical communication",
            "excellent communication",
            "communication skills",
            "communicate technical concepts",
        ),
        "evidence": (
            "engineering documentation",
            "operational runbooks",
            "technical and non-technical",
            "escalation point",
            "team lead",
            "cross-functional",
            "cross-team",
            "stakeholder",
        ),
        "standalone": True,
    },
    {
        "requirement": ("lead complex technical initiatives", "lead cross-team"),
        "evidence": (
            "led migration",
            "led rack-scale",
            "team lead",
            "escalation point",
            "cross-team",
        ),
        "standalone": True,
    },
    {
        "requirement": ("written and verbal communication",),
        "evidence": (
            "engineering documentation",
            "operational runbooks",
            "technical and non-technical",
            "escalation point",
        ),
        "standalone": True,
    },
    {
        "requirement": ("independently on substantial technical problems",),
        "evidence": ("designed and built", "owned", "led", "escalation point"),
        "standalone": True,
    },
    {
        "requirement": ("mentoring", "less experienced engineers"),
        "evidence": ("team lead", "led the", "technical lead", "escalation point"),
        "standalone": True,
    },
    {
        "requirement": ("storage systems knowledge",),
        "evidence": (
            "storage operations",
            "storage clusters",
            "storage migrations",
            "nfs",
            "san",
        ),
        "standalone": True,
    },
    {
        "requirement": (
            "distributed and high-performance storage",
            "clustered and parallel file systems",
            "distributed object storage",
            "enterprise-grade storage systems",
        ),
        "evidence": (
            "hpc storage",
            "storage clusters",
            "parallel file system",
            "lustre",
            "gpfs",
            "spectrum scale",
            "ceph",
            "object storage",
            "enterprise storage",
        ),
        "standalone": True,
    },
    {
        "requirement": ("ai tools", "ai-native development workflow"),
        "evidence": ("openai", "langchain", "ai assistant", "ai infrastructure"),
        "standalone": True,
    },
)

_ADVANCED_NETWORK_REQUIREMENTS = (
    "control plane",
    "data plane",
    "failure domains",
    "bgp",
    "ospf",
    "evpn",
    "vxlan",
    "mlag",
    "lacp",
)


def _compound_operational_design_is_supported(
    qualification: str,
    supported_text: str,
) -> bool:
    """Infer bounded design guidance only when leadership and scale coexist."""

    if not (
        "engineering design limitations" in qualification
        and "guidance to teams" in qualification
        and "scale their services" in qualification
    ):
        return False
    leadership_evidence = (
        "technical lead",
        "team lead",
        "escalation point",
        "cross-functional",
        "cross-team",
        "architecture",
        "design decision",
    )
    scale_evidence = (
        "capacity planning",
        "performance tuning",
        "performance optimization",
        "scalability",
        "scaled",
        "cost optimization",
        "operating constraints",
    )
    return any(marker in supported_text for marker in leadership_evidence) and any(
        marker in supported_text for marker in scale_evidence
    )


def _bounded_capability_evidence_supports(
    qualification: str,
    *,
    supported_text: str,
) -> bool:
    """Combine explicit technical evidence without combining generic keywords."""

    required_groups = [
        group
        for group in _BOUNDED_CAPABILITY_EVIDENCE
        if any(_contains_phrase(qualification, marker) for marker in group["requirement"])
    ]
    if not required_groups:
        return False
    if len(required_groups) == 1 and not required_groups[0].get("standalone", False):
        return False

    if any(
        _contains_phrase(qualification, marker)
        for marker in _ADVANCED_NETWORK_REQUIREMENTS
    ) and not any(
        _contains_phrase(supported_text, marker)
        for marker in _ADVANCED_NETWORK_REQUIREMENTS
    ):
        return False

    return all(
        any(_contains_phrase(supported_text, marker) for marker in group["evidence"])
        for group in required_groups
    )


def _broad_experience_duration_is_supported(
    qualification: str,
    supported_text: str,
) -> bool:
    """Compare explicit years only for broad engineering or industry experience."""

    required = re.search(r"\b(\d+)\+?\s+years?\b", qualification)
    if required is None or not any(
        marker in qualification
        for marker in (
            "hands-on engineering",
            "relevant industry experience",
            "hpc experience",
        )
    ):
        return False
    if any(
        marker in qualification
        for marker in (
            "software development",
            "software engineering",
            "security engineering",
            "data engineering",
        )
    ):
        return False
    resume_years = [
        int(value)
        for value in re.findall(r"\b(\d+)\+?\s+years?\b", supported_text)
    ]
    return bool(resume_years and max(resume_years) >= int(required.group(1)))


def _alternative_capability_is_supported(
    requirement: str,
    *,
    resume_segments: list[str],
) -> bool:
    """Accept one coherently evidenced option from a real alternative list."""

    if " or " not in requirement or "or equivalent experience" in requirement:
        return False
    option_text = requirement.split(" with ", 1)[-1]
    for option in re.split(r",|\bor\b", option_text):
        cleaned = clean_text(option).strip(" .;:-")
        cleaned = re.sub(
            r"^(?:and|solid experience|experience|proficiency)\s+(?:with|in)?\s*",
            "",
            cleaned,
        )
        tokens = _qualification_evidence_tokens(cleaned)
        if len(tokens) < 2:
            continue
        if any(
            all(
                token in set(_qualification_evidence_tokens(segment))
                for token in tokens
            )
            for segment in resume_segments
        ):
            return True
    return False


def _resume_evidence_segments(resume_text: str) -> list[str]:
    """Keep evidence within one résumé statement instead of the whole document."""

    segments = [
        clean_text(segment)
        for segment in re.split(
            r"(?:\r?\n|[•●▪]|(?<=[.!?])\s+)",
            resume_text,
        )
        if clean_text(segment)
    ]
    return segments or [clean_text(resume_text)]


def _qualification_evidence_tokens(value: str) -> list[str]:
    """Return distinct evidence-bearing words with light plural normalization."""

    tokens: list[str] = []
    for raw_token in re.findall(r"[a-z0-9+#.]+", value.lower()):
        if raw_token in _QUALIFICATION_EVIDENCE_STOP_WORDS:
            continue
        token = raw_token
        if len(token) > 4 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        if token not in tokens:
            tokens.append(token)
    # These phrases describe the same infrastructure capability in ordinary
    # engineering language. Expand them before comparison so Junior can infer
    # equivalent experience without treating every broad systems word as equal.
    if "distributed compute" in value.lower():
        for equivalent in ("distributed", "system", "compute", "platform"):
            if equivalent not in tokens:
                tokens.append(equivalent)
    return tokens


def _resume_shows_required_degree(
    resume_text: str,
    required_disciplines: list[str],
) -> bool:
    """Require the degree credential and discipline to appear together."""

    degree_marker = r"(?:bachelor(?:'s)?|b\.s\.|\bbs\b|degree)"
    for discipline in required_disciplines:
        for alias in _DEGREE_DISCIPLINES[discipline]:
            escaped_alias = re.escape(alias)
            if re.search(
                rf"(?:{degree_marker}.{{0,100}}{escaped_alias}|"
                rf"{escaped_alias}.{{0,100}}{degree_marker})",
                resume_text,
            ):
                return True
    return False


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
        required_marker_count = sum(
            1 for marker in markers if _contains_phrase(required_text, marker)
        )
        central_to_requirements = required_marker_count >= (
            1
            if discipline
            in {"software engineering", "data engineering", "security engineering"}
            else 2
        )
        if discipline in _DISCIPLINES_REQUIRING_DESCRIPTION_CONFIRMATION:
            central_to_title = central_to_title and central_to_requirements
        supported = any(_contains_phrase(supported_text, marker) for marker in markers)
        if (central_to_title or central_to_requirements) and not supported:
            if discipline == "civil, structural, or architectural engineering":
                critical.append(
                    "No Civil, Structural, and Architectural (CSA) experience"
                )
            elif discipline == "software engineering" and (
                software_years := re.search(
                    r"\b(\d+\+?)\s+years?\b[^.]{0,100}"
                    r"(?:software development|software engineering)",
                    required_text,
                )
            ):
                critical.append(
                    "No clear résumé evidence of "
                    f"{software_years.group(1)} years of professional "
                    "software development"
                )
            else:
                critical.append(
                    f"central discipline requires {discipline} experience"
                )

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
    if "go" in aliases and not (
        _contains_phrase(lowered, "golang")
        or re.search(
            r"\b(?:go\s+(?:experience|language|programming|developer)|"
            r"(?:proficiency|experience|programming)\s+(?:with|in)\s+go)\b",
            lowered,
        )
    ):
        # The English verb in "go deep on macOS" is not the Go language.
        return False

    offers_alternatives = any(
        marker in lowered
        for marker in (" one of ", " any of ", " or ", " such as ", " e.g.", " including ")
    )
    return not offers_alternatives


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

    family_aliases = {
        "software engineering": {"software development", "software developer"},
        "security engineering": {"cybersecurity", "cyber security"},
    }
    for family, title_markers in _AVOID_ROLE_FAMILIES.items():
        family_is_configured = bool(
            normalized_avoid & ({family} | family_aliases.get(family, set()))
        )
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

    if _has_dominant_occupation_conflict(
        title=title,
        candidate_profile=candidate_profile,
    ):
        return "the job's central occupation does not align with this profile's target work"

    if _role_alignment_is_confirmed(
        title=title,
        candidate_profile=candidate_profile,
    ):
        return None

    # A genuinely generic title can be clarified by several matching duties.
    # A concrete different profession (sales, construction, finance, and so on)
    # cannot be converted into a target role merely because it uses familiar tools.
    title_words = _meaningful_role_words(title)
    if (
        len(evidence) >= 4
        and title_words
        and title_words <= _OCCUPATION_NEUTRAL_TITLE_WORDS
    ):
        return None

    return "the job title and required work do not align with this profile's target work"


def _has_dominant_occupation_conflict(
    *,
    title: str,
    candidate_profile: CandidateProfile,
) -> bool:
    """Keep a shared work setting from disguising a different profession."""

    exclusive_families = (
        (
            "environmental health and safety",
            (
                "environmental health & safety",
                "environmental health and safety",
                "health & safety",
                "health and safety",
                "ehs",
            ),
        ),
    )
    profile_text = " ".join(
        candidate_profile.target_roles + candidate_profile.credible_adjacent
    ).lower()
    for _family, markers in exclusive_families:
        if any(_contains_phrase(title, marker) for marker in markers):
            return not any(
                _contains_phrase(profile_text, marker) for marker in markers
            )
    return False


def _role_alignment_is_confirmed(
    *,
    title: str,
    candidate_profile: CandidateProfile,
) -> bool:
    """Compare actual work families instead of treating titles as synonyms."""

    if not candidate_profile.target_roles:
        return True

    if _title_has_specific_target_role(
        title=title,
        candidate_profile=candidate_profile,
    ):
        return True

    # A skill can appear in work from an entirely different profession. Only
    # desired and explicitly adjacent roles may establish title alignment;
    # strengths still contribute responsibility evidence separately.
    profile_values = candidate_profile.target_roles + candidate_profile.credible_adjacent
    title_words = _meaningful_role_words(title)
    profile_words: set[str] = set()
    for value in profile_values:
        profile_words.update(_meaningful_role_words(clean_text(value).lower()))

    shared_words = title_words & profile_words
    if shared_words - _BROAD_ROLE_CONTEXT_WORDS:
        return True

    title_families = _role_families(title)
    profile_families: set[str] = set()
    for value in profile_values:
        profile_families.update(_role_families(clean_text(value).lower()))
    return bool(title_families & profile_families)


def _title_has_specific_target_role(
    *,
    title: str,
    candidate_profile: CandidateProfile,
) -> bool:
    """Require more than a generic one-word occupation for title certainty."""

    for target_role in candidate_profile.target_roles:
        normalized_role = clean_text(target_role).lower()
        if (
            len(re.findall(r"[a-z0-9+#]+", normalized_role)) >= 2
            and _contains_phrase(title, normalized_role)
        ):
            return True
    return False


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
    # Some APIs flatten every HTML block into one paragraph. Restore section
    # boundaries before parsing so "Qualifications Required Qualifications:"
    # is interpreted the same way as a normally formatted job description.
    decoded = re.sub(
        r"(?i)\bqualifications\s+(?=(?:required(?:/minimum)?|minimum|basic|preferred)\s+qualifications?)",
        "Qualifications\n",
        decoded,
    )
    # Only headings known to survive as inline Eightfold text belong here.
    # Broad phrases such as "the role" or "qualifications" also occur in
    # ordinary sentences and must not split a requirement mid-sentence.
    inline_headings = (
        "additional required qualifications",
        "additional preferred qualifications",
        "required/minimum qualifications",
        "required minimum qualifications",
        "required qualifications",
        "minimum qualifications",
        "basic qualifications",
        "preferred qualifications",
        "other requirements",
        "responsibilities",
    )
    heading_pattern = "|".join(re.escape(heading) for heading in inline_headings)
    decoded = re.sub(
        rf"(?i)(?<![\w/])({heading_pattern})\s*:?[ \t]*",
        lambda match: f"\n{match.group(1)}\n",
        decoded,
    )
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


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    deduped_values: list[str] = []

    for value in values:
        if value not in deduped_values:
            deduped_values.append(value)

    return deduped_values
