"""Tests how resume evidence and gaps are identified for a job posting."""

from dataclasses import replace

import pytest

from job_radar.candidate_profile import CandidateProfile, CandidateResumeConfig
from job_radar.models import JobPosting
from job_radar.resume_match import match_resume_to_posting


def make_profile() -> CandidateProfile:
    return CandidateProfile(
        name="Test User",
        compensation_floor_usd=160000,
        preferred_base_usd=185000,
        resume=CandidateResumeConfig(source_path="resume.md"),
        core_strengths=[
            "Linux infrastructure",
            "HPC operations",
            "cluster systems",
            "datacenter operations",
        ],
        credible_adjacent=["SRE", "GPU infrastructure"],
        learning_or_gap=[
            "production Kubernetes ownership",
            "security engineering",
            "heavy software engineering",
        ],
        avoid=["frontend"],
        target_roles=[
            "Platform Engineer",
            "Infrastructure Engineer",
            "Site Reliability Engineer",
        ],
    )


def make_posting(title: str, description: str) -> JobPosting:
    return JobPosting(
        company_key="test",
        company_name="Test Company",
        source_type="greenhouse",
        source_url="https://example.com/job",
        title=title,
        location="Remote",
        description=description,
    )


def test_match_resume_to_posting_returns_strong_evidence() -> None:
    posting = make_posting(
        title="Senior Linux Infrastructure Engineer",
        description=(
            "Operate Linux infrastructure, HPC operations, cluster systems, "
            "and datacenter operations."
        ),
    )
    resume_text = (
        "Senior infrastructure engineer with Linux infrastructure, HPC operations, "
        "cluster systems, and datacenter operations experience."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Very Strong"
    assert result.evidence == [
        "Linux infrastructure",
        "HPC operations",
        "cluster systems",
        "datacenter operations",
    ]
    assert result.gaps == []


def test_match_resume_to_posting_reports_gap() -> None:
    posting = make_posting(
        title="Senior SRE",
        description="Own Linux infrastructure and production Kubernetes ownership.",
    )
    resume_text = "Linux infrastructure and SRE experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Medium"
    assert result.evidence == ["Linux infrastructure", "SRE"]
    assert result.gaps == ["production Kubernetes ownership"]


def test_match_resume_to_posting_reports_configured_gap_without_title_guessing() -> None:
    posting = make_posting(
        title="Senior Platform Engineer",
        description=(
            "Operate Linux infrastructure and partner with security engineering "
            "teams on infrastructure security improvements."
        ),
    )
    resume_text = "Linux infrastructure and platform operations experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Medium"
    assert result.evidence == ["Linux infrastructure"]
    assert result.gaps == ["security engineering"]
    assert not result.has_critical_gap


def test_scattered_words_do_not_invent_a_configured_security_gap() -> None:
    posting = make_posting(
        title="HPC Technical Consultant",
        description=(
            "Key Responsibilities\n"
            "Monitor HPC compute, network, and storage infrastructure. Perform Linux "
            "system administration and troubleshoot server hardware.\n"
            "Minimum Qualifications\n"
            "US citizenship and ability to obtain a security clearance.\n"
            "Preferred Qualifications\n"
            "Experience in engineering organizations and HPC operations."
        ),
    )
    resume_text = "Linux infrastructure, HPC operations, and datacenter operations."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Weak"
    assert "security engineering" not in result.gaps
    assert not result.has_critical_gap


def test_kernel_development_is_not_mistaken_for_linux_operations() -> None:
    posting = make_posting(
        title="Principal Linux Kernel Developer",
        description=(
            "Key Responsibilities\n"
            "Lead architecture and design of Linux kernel components and contribute "
            "patches to upstream open-source communities.\n"
            "Required Qualifications\n"
            "Expert C programming and deep Linux kernel internals experience.\n"
            "8 years of kernel-level software development."
        ),
    )
    resume_text = "Linux infrastructure, HPC operations, and cluster administration."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert "central discipline requires software engineering experience" in result.gaps
    assert result.has_critical_gap


def test_match_resume_to_posting_rejects_required_go_for_non_software_profile() -> None:
    posting = make_posting(
        title="Software Engineer, Infrastructure",
        description=(
            "Required Qualifications\n"
            "- Strong Go experience building production services\n"
            "- Experience with distributed systems\n"
            "Preferred Qualifications\n"
            "- Rust experience"
        ),
    )
    resume_text = "Linux infrastructure, HPC, Python automation, and SRE experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert "central discipline requires software engineering experience" in result.gaps
    assert "required Go experience is not shown in the résumé" in result.gaps
    assert "required Rust experience is not shown in the résumé" not in result.gaps
    assert result.has_critical_gap


def test_match_resume_to_posting_keeps_real_infrastructure_role_reviewable() -> None:
    posting = make_posting(
        title="Senior Infrastructure Engineer",
        description=(
            "Required Qualifications\n"
            "- Experience operating Linux infrastructure and cluster systems\n"
            "Preferred Qualifications\n"
            "- Kubernetes ownership"
        ),
    )
    resume_text = "Linux infrastructure, HPC operations, and cluster systems."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Medium"
    assert not result.has_critical_gap


def test_match_resume_to_posting_reports_security_gap_for_security_focused_role() -> None:
    posting = make_posting(
        title="Infrastructure Security Engineer",
        description="Own Linux infrastructure and security engineering programs.",
    )
    resume_text = "Linux infrastructure and platform operations experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert result.evidence == ["Linux infrastructure"]
    assert result.gaps == [
        "security engineering",
        "central discipline requires security engineering experience",
    ]
    assert result.has_critical_gap


def test_match_resume_to_posting_reads_required_qualifications_from_html() -> None:
    posting = make_posting(
        title="Network Site Reliability Engineer",
        description=(
            "&lt;p&gt;About the company and its infrastructure platform.&lt;/p&gt;"
            "&lt;h3&gt;Required Qualifications&lt;/h3&gt;"
            "&lt;ul&gt;&lt;li&gt;Strong Go experience building production services"
            "&lt;/li&gt;&lt;li&gt;Linux infrastructure operations&lt;/li&gt;&lt;/ul&gt;"
            "&lt;h3&gt;Preferred Qualifications&lt;/h3&gt;"
            "&lt;li&gt;Rust experience&lt;/li&gt;"
        ),
    )
    resume_text = "Linux infrastructure, Python automation, and SRE experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert "required Go experience is not shown in the résumé" in result.gaps
    assert "required Rust experience is not shown in the résumé" not in result.gaps


def test_match_resume_to_posting_rejects_unrelated_role_using_boilerplate_terms() -> None:
    posting = make_posting(
        title="Government Relations Representative",
        description=(
            "About the company\n"
            "We build Linux infrastructure and GPU clusters.\n"
            "About the Role\n"
            "Build relationships with elected officials and regulators."
        ),
    )
    resume_text = "Linux infrastructure, HPC operations, and cluster systems."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert result.evidence == []
    assert (
        "the job title and required work do not align with this profile's target work"
        in result.gaps
    )


def test_match_resume_to_posting_respects_profile_excluded_role_family() -> None:
    posting = make_posting(
        title="Director of Product, Infrastructure",
        description="Lead product strategy for an infrastructure platform.",
    )
    resume_text = "Linux infrastructure, HPC operations, and cluster systems."
    profile = replace(
        make_profile(),
        avoid=["frontend", "product management"],
    )

    result = match_resume_to_posting(posting, profile, resume_text)

    assert result.label == "Poor Fit"
    assert "the role is in the excluded product management job family" in result.gaps


def test_match_resume_to_posting_does_not_require_every_technology_option() -> None:
    posting = make_posting(
        title="Infrastructure Engineer",
        description=(
            "Required Qualifications\n"
            "- Experience with one of AWS, Azure, or GCP\n"
            "- Linux infrastructure operations"
        ),
    )
    resume_text = "Linux infrastructure and AWS operations experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert not any("required Azure" in gap for gap in result.gaps)
    assert not any("required GCP" in gap for gap in result.gaps)


def test_two_broad_resume_terms_do_not_rescue_unrelated_role() -> None:
    posting = make_posting(
        title="Director, Marketing Operations",
        description=(
            "About the Role\n"
            "Lead marketing operations for an AI infrastructure company. "
            "Partner with reliability teams."
        ),
    )
    resume_text = "AI infrastructure and reliability engineering experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert (
        "the job title and required work do not align with this profile's target work"
        in result.gaps
    )


def test_configured_manager_exclusion_blocks_manager_title() -> None:
    posting = make_posting(
        title="Infrastructure Engineering Manager",
        description="Manage Linux infrastructure engineers.",
    )
    resume_text = "Linux infrastructure and platform operations experience."
    profile = replace(make_profile(), avoid=["Manager"])

    result = match_resume_to_posting(posting, profile, resume_text)

    assert result.label == "Poor Fit"
    assert "the role is in the excluded manager job family" in result.gaps


def test_configured_management_exclusion_blocks_group_leader_title() -> None:
    posting = make_posting(
        title="HPC Storage Systems Group Leader",
        description="Manage the storage systems group and its engineering staff.",
    )
    resume_text = "Linux infrastructure, HPC operations, and storage systems experience."
    profile = replace(make_profile(), avoid=["Management"])

    result = match_resume_to_posting(posting, profile, resume_text)

    assert result.label == "Poor Fit"
    assert "the role is in the excluded manager job family" in result.gaps


def test_configured_management_exclusion_does_not_block_technical_lead_title() -> None:
    posting = make_posting(
        title="Lead Senior Infrastructure Engineer",
        description="Operate Linux infrastructure and HPC cluster systems.",
    )
    resume_text = "Linux infrastructure, HPC operations, and cluster systems experience."
    profile = replace(make_profile(), avoid=["Management"])

    result = match_resume_to_posting(posting, profile, resume_text)

    assert result.label != "Poor Fit"
    assert "the role is in the excluded manager job family" not in result.gaps


def test_management_exclusion_does_not_block_vulnerability_management_work() -> None:
    posting = make_posting(
        title="Infrastructure Vulnerability Management Engineer",
        description="Operate Linux infrastructure and remediate vulnerabilities.",
    )
    resume_text = "Linux infrastructure and platform operations experience."
    profile = replace(make_profile(), avoid=["Management"])

    result = match_resume_to_posting(posting, profile, resume_text)

    assert "the role is in the excluded manager job family" not in result.gaps


def test_systems_administrator_aligns_with_infrastructure_profile() -> None:
    posting = make_posting(
        title="Senior Systems Administrator",
        description=(
            "Required Qualifications\n"
            "- Experience operating Linux infrastructure and cluster systems"
        ),
    )
    resume_text = "Linux infrastructure and cluster systems administration."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Medium"
    assert not result.has_critical_gap


def test_generic_systems_word_does_not_align_unrelated_spacecraft_role() -> None:
    posting = make_posting(
        title="Human Landing System (HLS) Engineer - APS Systems (SME1)",
        description=(
            "Required Qualifications\n"
            "- Engineering degree and 20 years of aerospace engineering experience\n"
            "- Liquid propulsion design, analysis, integration, and testing\n"
            "- Experience with reaction-control thrusters and spacecraft fluid systems\n"
            "Responsibilities\n"
            "- Support NASA human landing propulsion-system engineering"
        ),
    )
    resume_text = (
        "Senior infrastructure engineer with Linux infrastructure, HPC operations, "
        "cluster systems, datacenter operations, and platform reliability experience."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert result.evidence == []
    assert result.has_critical_gap
    assert (
        "the job title and required work do not align with this profile's target work"
        in result.gaps
    )


def test_core_strength_alone_does_not_turn_unrelated_role_into_target_work() -> None:
    posting = make_posting(
        title="Marketing Automation Specialist",
        description=(
            "Required Qualifications\n"
            "- Marketing automation and campaign-management experience\n"
            "Responsibilities\n"
            "- Build email campaigns and manage customer segments"
        ),
    )
    profile = replace(
        make_profile(),
        core_strengths=[*make_profile().core_strengths, "automation"],
    )
    resume_text = "Infrastructure automation and Linux operations experience."

    result = match_resume_to_posting(posting, profile, resume_text)

    assert result.label == "Poor Fit"
    assert result.has_critical_gap


@pytest.mark.parametrize(
    ("title", "description"),
    [
        (
            "Thermal Systems Engineer",
            (
                "Required qualifications include a mechanical or aerospace engineering "
                "degree and experience with spacecraft thermal analysis, heat transfer, "
                "thermal vacuum testing, and flight-hardware qualification."
            ),
        ),
        (
            "Financial Systems Analyst",
            (
                "Required qualifications include accounting operations, financial "
                "reporting, ERP administration, general-ledger controls, and audit support."
            ),
        ),
        (
            "Produce/Assistant Department Leader",
            (
                "Manage produce inventory, merchandising, food safety, department budgets, "
                "associate schedules, customer service, and in-store sales promotions."
            ),
        ),
        (
            "Courtesy Clerk/Grocery Bagger",
            (
                "Bag groceries, retrieve carts, clean customer areas, assist shoppers, "
                "and follow retail store safety and food-handling procedures."
            ),
        ),
    ],
)
def test_generic_overlap_does_not_surface_clearly_unrelated_work(
    title: str,
    description: str,
) -> None:
    posting = make_posting(title=title, description=description)
    resume_text = (
        "Senior infrastructure engineer with Linux infrastructure, HPC operations, "
        "cluster systems, datacenter operations, and platform reliability experience."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert result.has_critical_gap
    assert (
        "the job title and required work do not align with this profile's target work"
        in result.gaps
    )


def test_datacenter_architect_role_detects_civil_design_discipline_gap() -> None:
    posting = make_posting(
        title="Data Center Architect, CSA",
        description=(
            "Required Qualifications\n"
            "- Civil, structural, or architectural engineering experience\n"
            "- Lead hyperscale facility design and construction oversight\n"
            "- Apply building codes and professional engineering standards"
        ),
    )
    resume_text = (
        "Linux infrastructure, HPC operations, cluster systems, datacenter "
        "operations, and AI infrastructure."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert result.has_critical_gap
    assert any(
        "civil, structural, or architectural engineering" in gap
        for gap in result.gaps
    )


def test_hpc_scientific_support_role_reports_required_computing_gaps() -> None:
    posting = make_posting(
        title="HPC Scientific Support Engineer",
        description=(
            "Minimum Qualifications\n"
            "- Experience supporting scientific users and debugging HPC applications\n"
            "- Strong Fortran experience\n"
            "- Experience with MPI and OpenMP\n"
            "- Experience creating user documentation and delivering user training\n"
            "Preferred Qualifications\n"
            "- CUDA and OpenACC"
        ),
    )
    resume_text = (
        "Linux infrastructure, HPC operations, cluster systems, storage systems, "
        "networking, and infrastructure automation."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert result.has_critical_gap
    assert any(gap.startswith("required Fortran experience") for gap in result.gaps)
    assert any(gap.startswith("required MPI experience") for gap in result.gaps)
    assert any(gap.startswith("required OpenMP experience") for gap in result.gaps)
    assert not any(gap.startswith("required CUDA experience") for gap in result.gaps)
    assert not any(gap.startswith("required OpenACC experience") for gap in result.gaps)


def test_incomplete_listing_teaser_cannot_report_no_gaps() -> None:
    posting = make_posting(
        title="Kubernetes Platform Architect",
        description="",
    )
    resume_text = (
        "Linux infrastructure, HPC operations, cluster systems, storage systems, "
        "networking, automation, and Kubernetes operations."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Weak"
    assert result.has_critical_gap
    assert result.requirements_reviewed == []
    assert result.gaps == [
        "The collected posting did not include enough job-description detail "
        "to verify its required qualifications."
    ]


def test_datacenter_architect_reads_employer_specific_requirement_heading() -> None:
    posting = make_posting(
        title="Data Center Architect, CSA",
        description=(
            "You may be a good fit if\n"
            "- You have civil, structural, or architectural engineering experience\n"
            "- You have led hyperscale facility design and construction oversight\n"
            "- You apply building codes and professional engineering standards\n"
            "What you will do\n"
            "- Lead the architecture of complex datacenter construction programs"
        ),
    )
    resume_text = (
        "Linux infrastructure, HPC operations, cluster systems, datacenter "
        "operations, and AI infrastructure."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert result.has_critical_gap
    assert any(
        "civil, structural, or architectural engineering" in gap
        for gap in result.gaps
    )


def test_legitimate_adjacent_infrastructure_role_remains_reviewable() -> None:
    posting = make_posting(
        title="HPC Scientific Support Engineer",
        description=(
            "Support Linux HPC clusters, storage systems, schedulers, networking, "
            "automation, incident response, and Kubernetes-based research platforms."
        ),
    )
    profile = replace(
        make_profile(),
        credible_adjacent=["HPC operations", "Kubernetes operations"],
    )
    resume_text = (
        "Linux infrastructure, HPC operations, cluster systems, storage systems, "
        "networking, automation, and incident response."
    )

    result = match_resume_to_posting(posting, profile, resume_text)

    assert not result.has_critical_gap
    assert result.label in {"Strong", "Medium"}


def test_unfamiliar_title_with_responsibility_evidence_stays_below_top_match() -> None:
    posting = make_posting(
        title="Senior Technical Specialist",
        description=(
            "Operate Linux infrastructure, HPC operations, cluster systems, "
            "and datacenter operations."
        ),
    )
    resume_text = (
        "Linux infrastructure, HPC operations, cluster systems, "
        "and datacenter operations."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Medium"
    assert not result.has_critical_gap


def test_match_resume_to_posting_rejects_supply_chain_discipline() -> None:
    posting = make_posting(
        title="Hardware Sourcing and Supply Chain Lead",
        description="Own strategic sourcing, procurement, and supplier negotiations.",
    )
    resume_text = "Linux infrastructure, HPC operations, and hardware systems experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert "central discipline requires supply chain experience" in result.gaps


def test_match_resume_to_posting_rejects_tax_discipline() -> None:
    posting = make_posting(
        title="Infrastructure Tax Lead",
        description="Own tax accounting and tax compliance for infrastructure assets.",
    )
    resume_text = "Linux infrastructure and datacenter operations experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert "central discipline requires tax and accounting experience" in result.gaps


def test_match_resume_to_posting_rejects_digital_forensics_discipline() -> None:
    posting = make_posting(
        title="Senior Digital Forensics Automation Specialist",
        description="Required Qualifications\nDigital forensics and forensic analysis.",
    )
    resume_text = "Linux infrastructure and Python automation experience."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert "central discipline requires digital forensics experience" in result.gaps


def test_match_resume_to_posting_returns_unknown_without_profile() -> None:
    posting = make_posting(
        title="Senior SRE",
        description="Linux infrastructure role.",
    )

    result = match_resume_to_posting(posting, None, None)

    assert result.label == "Unknown"
    assert result.evidence == []
    assert result.gaps == []
