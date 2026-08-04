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

    assert result.label == "Medium"
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
    assert "No clear résumé evidence of 8 years of professional software development" in result.gaps
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


def test_match_resume_reports_unsupported_facilities_requirements() -> None:
    posting = make_posting(
        title="Data Center Design Execution Lead",
        description=(
            "Required Qualifications\n"
            "Experience managing design execution or technical programs in "
            "partnership with external design/construction firms.\n"
            "Working familiarity with mechanical, electrical, and cooling systems "
            "sufficient to manage technical discussions.\n"
            "Experience managing design change processes, RFIs, and construction "
            "documentation workflows.\n"
            "Familiarity with industry standards, building codes, and safety "
            "standards applicable to mission-critical facilities.\n"
            "BS in Mechanical Engineering, Electrical Engineering, Architecture, "
            "or related field."
        ),
    )
    resume_text = "HPC operations, datacenter operations, and AI infrastructure."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert result.has_critical_gap
    assert len(result.gaps) == 5
    assert (
        "No experience managing design execution with external design or construction firms"
        in result.gaps
    )
    assert (
        "No working knowledge of mechanical, electrical, and cooling systems"
        in result.gaps
    )
    assert (
        "No experience managing design changes, RFIs, and construction documentation"
        in result.gaps
    )
    assert any("building-code standards" in gap for gap in result.gaps)
    assert any("bachelor's degree" in gap for gap in result.gaps)


def test_match_resume_reads_required_and_ignores_preferred_headings() -> None:
    posting = make_posting(
        title="Data Center Design Execution Lead",
        description=(
            "&lt;p&gt;&lt;strong&gt;Qualifications&lt;/strong&gt;&lt;/p&gt;"
            "&lt;p&gt;&lt;strong&gt;Required&lt;/strong&gt;&lt;/p&gt;"
            "&lt;ul&gt;&lt;li&gt;Experience managing design change processes, RFIs, "
            "and construction documentation workflows.&lt;/li&gt;"
            "&lt;li&gt;BS in Mechanical Engineering or related field.&lt;/li&gt;&lt;/ul&gt;"
            "&lt;p&gt;Preferred&lt;/p&gt;&lt;ul&gt;"
            "&lt;li&gt;Professional Engineer license.&lt;/li&gt;&lt;/ul&gt;"
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "HPC operations and datacenter infrastructure.",
    )

    assert any("design changes" in gap for gap in result.gaps)
    assert any("bachelor's degree" in gap for gap in result.gaps)
    assert all("Professional Engineer" not in gap for gap in result.gaps)


def test_one_supported_option_satisfies_an_explicit_alternative_list() -> None:
    posting = make_posting(
        title="Infrastructure Engineer",
        description=(
            "Required\nProficiency with scripting languages such as Python, Go, "
            "Bash, or equivalent."
        )
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Built extensive Python automation for infrastructure operations.",
    )

    assert result.gaps == []


def test_architecture_experience_does_not_count_as_architecture_degree() -> None:
    posting = make_posting(
        title="Facilities Engineer",
        description=(
            "Required Qualifications\n"
            "BS in Mechanical Engineering, Electrical Engineering, Architecture, "
            "or related field."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Designed Linux systems architecture and datacenter infrastructure.",
    )

    assert any("bachelor's degree" in gap for gap in result.gaps)


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


def test_software_development_avoidance_rejects_kernel_developer() -> None:
    posting = make_posting(
        title="Principal Linux Kernel Developer",
        description=(
            "Develop Linux kernel components and low-level software features."
        ),
    )
    profile = replace(make_profile(), avoid=["software development"])

    result = match_resume_to_posting(posting, profile, "Linux and HPC operations.")

    assert result.label == "Poor Fit"
    assert "the role is in the excluded software engineering job family" in result.gaps


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


def test_datacenter_context_does_not_rescue_environmental_safety_profession() -> None:
    posting = make_posting(
        title="Environmental Health & Safety Lead - Datacenter",
        description=(
            "Required Qualifications\n"
            "Deep experience leading EHS programs for hyperscale data centers "
            "or similarly complex industrial facilities."
        ),
    )
    resume_text = (
        "Datacenter operations, distributed compute, AI infrastructure, Linux, "
        "reliability engineering, and technical leadership."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert result.has_critical_gap
    assert any("central occupation" in gap for gap in result.gaps)


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
        "Civil, Structural, and Architectural (CSA)" in gap
        for gap in result.gaps
    )


def test_datacenter_csa_architect_gets_concise_capability_gaps() -> None:
    posting = make_posting(
        title="Data Center Architect, CSA",
        description=(
            "Required\n"
            "10+ years delivering mission-critical facility infrastructure, with "
            "6 years in hyperscale data center CSA design.\n"
            "Deep expertise across civil site development, structural design, and "
            "architectural programming.\n"
            "Experience as an owner's engineer or lead technical authority.\n"
            "Proficiency with building codes including IBC, IFC, ASCE 7, ACI 318, "
            "AISC, and FM Global.\n"
            "Ability to evaluate structural calculations and civil site plans.\n"
            "Clear communication with technical and non-technical audiences; "
            "ability to defend design decisions with incomplete information."
        ),
    )
    resume_text = (
        "Principal infrastructure engineer with 20 years designing large-scale "
        "Linux compute platforms and datacenter infrastructure. Led engineering "
        "teams, served as an escalation point, collaborated across engineering "
        "teams, and delivered design documents and operational runbooks."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.label == "Poor Fit"
    assert result.gaps == [
        "No Civil, Structural, and Architectural (CSA) experience",
        "No data center CSA design experience",
        "No experience as a lead technical authority",
        "No proficiency with building-code standards such as IBC, IFC, ASCE 7, "
        "ACI 318, AISC, or FM Global",
    ]


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


def test_generic_gap_keeps_complete_core_qualification_without_ellipsis() -> None:
    posting = make_posting(
        title="Detection Engineering & Response Lead",
        description=(
            "Required Qualifications\n"
            "- 6+ years in security operations, detection engineering, or incident "
            "response — with experience leading a global team"
        ),
    )
    resume_text = "Linux infrastructure, HPC operations, and platform engineering."

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert (
        "No clear résumé evidence of 6+ years in security operations, detection "
        "engineering, or incident response"
        in result.gaps
    )
    assert not any("…" in gap for gap in result.gaps)


def test_advanced_network_requirement_is_not_described_as_missing_basics() -> None:
    posting = make_posting(
        title="Forward Deployed Engineer - Physical AI Cloud Platform",
        description=(
            "Required Qualifications\n"
            "- Solid understanding of networking basics and how real networks fail "
            "(control plane vs data plane, latency/loss, failure domains)"
        ),
    )
    resume_text = (
        "Designed and operated datacenter and HPC networking infrastructure. "
        "Troubleshot production network incidents and automated network operations."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.gaps == [
        "No demonstrated advanced network failure-model expertise across control "
        "and data planes, failure domains, and latency or loss"
    ]
    assert all("networking basics" not in gap for gap in result.gaps)


def test_flattened_inline_required_and_preferred_headings_are_separated() -> None:
    posting = make_posting(
        title="Capacity Infrastructure Engineer",
        description=(
            "Responsibilities Build reliable compute systems. Qualifications "
            "Required Qualifications: 6+ years of professional software engineering "
            "experience. Preferred Qualifications: CUDA and PyTorch experience."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Operated Linux and HPC infrastructure.\nBuilt Python deployment scripts.",
    )

    assert result.requirements_reviewed == [
        "6+ years of professional software engineering experience."
    ]
    assert any("professional software development" in gap for gap in result.gaps)
    assert all("CUDA" not in gap and "PyTorch" not in gap for gap in result.gaps)


def test_two_of_two_missing_required_qualifications_are_decisive() -> None:
    posting = make_posting(
        title="Data Center Design Lead",
        description=(
            "Required Qualifications\n"
            "12+ years designing data centers.\n"
            "Direct electrical, mechanical, and architectural design experience."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Operated Linux HPC systems in datacenters.",
    )

    assert result.label == "Poor Fit"
    assert result.has_critical_gap


def test_optional_strong_plus_clause_is_not_a_required_gap() -> None:
    posting = make_posting(
        title="Infrastructure Solution Architect",
        description=(
            "What We're Looking For\n"
            "Customer-facing infrastructure architecture experience.\n"
            "Experience with SLAs and delivery commitments is a strong plus."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Designed and delivered infrastructure for internal engineering teams.",
    )

    assert all("SLA" not in requirement for requirement in result.requirements_reviewed)
    assert all("SLA" not in gap for gap in result.gaps)


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
        "Civil, Structural, and Architectural (CSA)" in gap
        for gap in result.gaps
    )


def test_candidate_profile_and_preferred_boundaries_are_interpreted_by_function() -> None:
    posting = make_posting(
        title="IT Systems Engineer, Client Platform Engineer",
        description=(
            "Responsibilities\n"
            "Operate the endpoint platform and automate patch management.\n"
            "You may be a good fit if you\n"
            "Have 8+ years building secure IT systems in complex environments\n"
            "Have managed endpoint fleets of thousands of macOS and Windows "
            "devices through a modern MDM\n"
            "Treat endpoint configuration as code through scripted deployments "
            "or full GitOps\n"
            "Go deep on macOS internals and remain hands on with Windows internals\n"
            "Strong candidates may also\n"
            "Bring proficiency in Swift or Go\n"
            "Technical Skills\n"
            "Device lifecycle automation including zero touch enrollment, patching, "
            "and software distribution\n"
            "Logistics\n"
            "Minimum education: Bachelor's degree or equivalent experience"
        ),
    )
    resume_text = (
        "Twenty years building Linux infrastructure and automating distributed "
        "systems with Python and PowerShell. Led complex cross-team projects."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert len(result.requirements_reviewed) == 5
    assert not any("Swift" in requirement for requirement in result.requirements_reviewed)
    assert result.label == "Poor Fit"
    assert result.gaps == [
        "No large-scale endpoint fleet or modern MDM management experience",
        "No endpoint configuration-as-code or device GitOps experience",
        "No demonstrated macOS endpoint-platform depth",
        "No fleet-scale zero-touch provisioning, patching, or software-distribution automation",
    ]


def test_added_bonus_heading_ends_required_qualification_section() -> None:
    posting = make_posting(
        title="Forward Deployed Engineer",
        description=(
            "We expect you to have:\n"
            "Customer-facing cloud platform deployment experience.\n"
            "It would be an added bonus if you have:\n"
            "Experience with a proprietary simulation platform.\n"
            "Key Employee Benefits:\n"
            "Health insurance and retirement benefits."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Built Linux infrastructure and automated HPC platforms.",
    )

    assert result.requirements_reviewed == [
        "Customer-facing cloud platform deployment experience."
    ]


def test_scattered_resume_words_do_not_prove_one_coherent_qualification() -> None:
    posting = make_posting(
        title="Forward Deployed Engineer",
        description=(
            "Required Qualifications\n"
            "Customer-facing deployment of AI cloud platforms in production."
        ),
    )
    resume_text = (
        "Supported internal customers with Linux incidents. "
        "Deployed storage firmware in datacenters. "
        "Operated a private cloud platform. "
        "Explored AI infrastructure architecture."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.gaps


def test_explicit_foundational_capabilities_can_reinforce_across_resume_lines() -> None:
    posting = make_posting(
        title="Site Reliability Engineer",
        description=(
            "Required Qualifications\n"
            "Proficiency in Linux systems, with expertise in Python and Bash "
            "scripting for automation.\n"
            "Ability to troubleshoot complex system issues, including hardware, "
            "software, and networking problems.\n"
            "Analytical and problem-solving skills focused on system performance.\n"
            "Working proficiency in English."
        ),
    )
    resume_text = (
        "Professional summary: Linux infrastructure and reliability engineering.\n"
        "Core competencies: hardware/software boundary troubleshooting and networking.\n"
        "Technologies: Python, Bash, and PowerShell automation.\n"
        "Improved cluster performance through root-cause analysis and remediation.\n"
        "Designed, documented, and operated large production environments for "
        "technical and non-technical partners."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.gaps == []


def test_advanced_network_design_is_not_inferred_from_generic_networking() -> None:
    posting = make_posting(
        title="Staff Network Site Reliability Engineer",
        description=(
            "Required Qualifications\n"
            "Networking expertise covering control plane vs data plane, latency, "
            "loss, and failure domains."
        ),
    )
    resume_text = (
        "Linux infrastructure and network operations.\n"
        "Reliability engineering and incident response."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.gaps


def test_simple_scripting_requirement_uses_explicit_resume_languages() -> None:
    posting = make_posting(
        title="Site Reliability Engineer",
        description="Required Qualifications\nScripting or programming skills.",
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Technologies: Python, Bash, and PowerShell automation.",
    )

    assert result.gaps == []


def test_working_conditions_and_welcome_language_do_not_become_required_gaps() -> None:
    posting = make_posting(
        title="Site Reliability Engineer",
        description=(
            "Required Qualifications\n"
            "Linux systems administration.\n"
            "Python is also welcome.\n"
            "Working Conditions\n"
            "The employee may occasionally lift equipment.\n"
            "Successful completion of a background check is required."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Operated large-scale Linux infrastructure.",
    )

    assert result.requirements_reviewed == ["Linux systems administration."]


def test_aspiration_language_is_not_a_resume_gap() -> None:
    posting = make_posting(
        title="Site Reliability Engineer",
        description=(
            "Required Qualifications\n"
            "Linux systems administration.\n"
            "Desire to be involved in backend development."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Operated large-scale Linux infrastructure.",
    )

    assert all("desire" not in gap.lower() for gap in result.gaps)


def test_documentation_and_tooling_are_inferred_from_explicit_resume_evidence() -> None:
    posting = make_posting(
        title="Staff Site Reliability Engineer",
        description=(
            "Required Qualifications\n"
            "Excellent written communication skills.\n"
            "Experience with modern infrastructure tooling and automating workflows."
        ),
    )
    resume_text = (
        "Delivered engineering documentation and operational runbooks.\n"
        "Automated infrastructure with Terraform, Ansible, Jenkins, and Kubernetes."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.gaps == []


def test_incident_and_postmortem_requirement_reports_only_missing_postmortem() -> None:
    posting = make_posting(
        title="Site Reliability Engineer",
        description=(
            "Required Qualifications\n"
            "Incident response and postmortem leadership experience."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Led incident response and restored critical Linux infrastructure.",
    )

    assert result.gaps == ["No demonstrated postmortem leadership experience"]


def test_core_hpc_monitoring_and_fabric_evidence_uses_named_resume_tools() -> None:
    posting = make_posting(
        title="HPC Infrastructure Engineer",
        description=(
            "Required Qualifications\n"
            "3+ years of hands-on HPC administration experience.\n"
            "Experience with Prometheus or Grafana monitoring platforms.\n"
            "Operational experience with InfiniBand or RDMA fabrics."
        ),
    )
    resume_text = (
        "Twenty years operating HPC and Slurm clusters.\n"
        "Deployed Prometheus and Grafana monitoring.\n"
        "Maintained InfiniBand and RDMA fabrics."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.gaps == []


def test_post_qualification_benefits_and_on_call_do_not_become_resume_gaps() -> None:
    posting = make_posting(
        title="Platform Engineer",
        description=(
            "Required Qualifications\n"
            "Linux infrastructure experience.\n"
            "Participate in on-call as required.\n"
            "Key Employee Benefits\n"
            "401(k) plan\n"
            "Parental leave\n"
            "What we can offer you\n"
            "A collaborative, supportive, and innovative environment."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Operated enterprise Linux infrastructure.",
    )

    assert result.requirements_reviewed == ["Linux infrastructure experience."]


def test_cross_layer_leadership_and_communication_use_explicit_resume_evidence() -> None:
    posting = make_posting(
        title="Principal Infrastructure Engineer",
        description=(
            "Required Qualifications\n"
            "Ability to resolve cross-layer hardware, firmware, kernel, and "
            "application issues.\n"
            "Ability to lead complex technical initiatives across teams.\n"
            "Effective communication and collaboration."
        ),
    )
    resume_text = (
        "Served as the escalation point for cross-layer failures and root cause analysis.\n"
        "Led rack-scale deployments and cross-team storage migrations.\n"
        "Delivered engineering documentation and operational runbooks."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.gaps == []


def test_stack_av_communication_and_scheduler_requirements_use_resume_evidence() -> None:
    posting = make_posting(
        title="Senior Compute Platform Engineer",
        description=(
            "Required Qualifications\n"
            "Ability to collaborate across teams and communicate technical "
            "concepts clearly.\n"
            "Experience with at least one batch scheduling system such as "
            "Kueue, Armada, Volcano, or Slurm."
        ),
    )
    resume_text = (
        "Served as a cross-functional technical lead and escalation point.\n"
        "Operated production HPC clusters and Slurm workload scheduling."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.gaps == []


def test_nvidia_storage_and_storage_automation_use_advanced_resume_evidence() -> None:
    posting = make_posting(
        title="Senior Storage Production Engineer - DGX Cloud",
        description=(
            "Required Qualifications\n"
            "Experience with distributed and high-performance storage solutions, "
            "including clustered and parallel file systems, distributed object "
            "storage, and enterprise-grade storage systems.\n"
            "Hands-on experience with infrastructure configuration management tools "
            "like Ansible, Chef, Puppet, and Terraform for automating storage deployments."
        ),
    )
    resume_text = (
        "Owned HPC storage clusters with Lustre parallel filesystems and Ceph object storage.\n"
        "Automated infrastructure deployments using Ansible and Terraform."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert all("distributed and high-performance storage" not in gap for gap in result.gaps)
    assert all("configuration management" not in gap for gap in result.gaps)


def test_basic_local_storage_does_not_satisfy_advanced_distributed_storage() -> None:
    posting = make_posting(
        title="Senior Storage Production Engineer",
        description=(
            "Required Qualifications\n"
            "Experience with distributed and high-performance storage solutions, "
            "including clustered and parallel file systems and distributed object storage."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Managed local server disks, backups, and ordinary file shares.",
    )

    assert result.gaps


def test_operational_design_guidance_uses_leadership_and_scaling_evidence() -> None:
    posting = make_posting(
        title="Site Reliability Engineer",
        description=(
            "Required Qualifications\n"
            "Understanding of engineering design limitations and ability to provide "
            "guidance to teams to scale their services to achieve desired performance "
            "within budget."
        ),
    )
    resume_text = (
        "Technical lead and escalation point for architecture and design decisions.\n"
        "Led capacity planning, performance tuning, scalability, and cost optimization."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.gaps == []


def test_broad_experience_years_and_degree_alternative_use_career_evidence() -> None:
    posting = make_posting(
        title="Infrastructure Engineer",
        description=(
            "Required Qualifications\n"
            "6+ years of hands-on engineering experience.\n"
            "Undergraduate degree or comparable training and equivalent relevant "
            "industry experience."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Infrastructure engineer with 20+ years of relevant industry experience.",
    )

    assert result.gaps == []


def test_soft_traits_are_not_presented_as_largest_resume_gaps() -> None:
    posting = make_posting(
        title="Datacenter Infrastructure Specialist",
        description=(
            "Required Qualifications\n"
            "High Agency.\n"
            "Operational Flexibility.\n"
            "Strategic Problem-Solver.\n"
            "Remote-First Operating Excellence."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Led complex infrastructure delivery and incident response.",
    )

    assert result.gaps == []


def test_leadership_storage_and_ai_tooling_use_explicit_resume_evidence() -> None:
    posting = make_posting(
        title="Principal Infrastructure Engineer",
        description=(
            "Required Qualifications\n"
            "Work independently on substantial technical problems.\n"
            "Experience mentoring less experienced engineers.\n"
            "Storage Systems Knowledge.\n"
            "Use AI tools to build scripts and automation."
        ),
    )
    resume_text = (
        "Team lead and escalation point who owned storage operations and NFS migrations.\n"
        "Built an OpenAI and LangChain assistant plus Python automation."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.gaps == []


def test_server_network_and_hyphenated_iac_use_named_resume_evidence() -> None:
    posting = make_posting(
        title="Infrastructure Systems Engineer",
        description=(
            "Required Qualifications\n"
            "Infrastructure-as-Code with Terraform or Ansible.\n"
            "Solid understanding of modern server architecture.\n"
            "Good knowledge of computer networks."
        ),
    )
    resume_text = (
        "Built rack-scale bare-metal systems with hardware management tooling.\n"
        "Automated infrastructure with Terraform and Ansible.\n"
        "Operated cluster networking, VLANs, and TCP/IP services."
    )

    result = match_resume_to_posting(posting, make_profile(), resume_text)

    assert result.gaps == []


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


def test_degree_or_equivalent_experience_can_be_supported_without_degree() -> None:
    posting = make_posting(
        title="Cloud Solution Architect",
        description=(
            "Required Qualifications\n"
            "Bachelor's degree in computer science or equivalent experience.\n"
            "Experience designing Linux cloud infrastructure."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Twenty years designing and operating Linux cloud infrastructure.",
    )

    assert not any("bachelor" in gap.lower() for gap in result.gaps)


def test_explicit_software_engineering_requirement_is_a_critical_gap() -> None:
    posting = make_posting(
        title="Capacity Infrastructure Engineer",
        description=(
            "Required Qualifications\n"
            "5+ years of professional software development experience in Python or Go."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Linux infrastructure operations and shell automation.",
    )

    assert result.has_critical_gap
    assert result.label == "Poor Fit"
    assert any("software" in gap.lower() for gap in result.gaps)


def test_match_resume_to_posting_returns_unknown_without_profile() -> None:
    posting = make_posting(
        title="Senior SRE",
        description="Linux infrastructure role.",
    )

    result = match_resume_to_posting(posting, None, None)

    assert result.label == "Unknown"
    assert result.evidence == []
    assert result.gaps == []


def test_explicit_tcpip_and_ansible_evidence_satisfies_named_requirements() -> None:
    posting = make_posting(
        title="Senior Linux Infrastructure Engineer",
        description=(
            "Required Qualifications\n"
            "Knowledge of TCP/IP network protocols and addressing.\n"
            "Experience with a configuration management platform such as Ansible, Puppet, or Chef."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Operated TCP/IP networks and automated Linux configuration with Ansible.",
    )

    assert not any("tcp/ip" in gap.lower() for gap in result.gaps)
    assert not any("configuration management" in gap.lower() for gap in result.gaps)


def test_observability_gap_summarizes_only_missing_advanced_practices() -> None:
    posting = make_posting(
        title="Site Reliability and Observability Engineer",
        description=(
            "Required Qualifications\n"
            "Experience with distributed tracing and application performance monitoring (APM)."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Built Prometheus metrics and Grafana dashboards for production infrastructure.",
    )

    assert result.gaps == [
        "No demonstrated distributed-tracing or application-performance-monitoring experience"
    ]


def test_advanced_network_gap_is_concise_despite_basic_vlan_evidence() -> None:
    posting = make_posting(
        title="Senior Network Engineer",
        description=(
            "Required Qualifications\n"
            "Design high-speed Ethernet networks using VLAN, LACP, MLAG, BGP, OSPF, EVPN, and VXLAN."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Designed and operated TCP/IP and VLAN network infrastructure.",
    )

    assert result.gaps == [
        "No demonstrated BGP, OSPF, EVPN, VXLAN, MLAG, or LACP network-design experience"
    ]


def test_production_kubernetes_requirement_is_not_satisfied_by_lab_exposure() -> None:
    posting = make_posting(
        title="Senior Cloud Native Platform Engineer",
        description=(
            "Required Qualifications\n"
            "Strong hands-on experience operating Kubernetes-based platforms in production."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Built a three-node Kubernetes k3s lab and deployed workloads with Helm.",
    )

    assert result.gaps == [
        "No demonstrated ownership of a production Kubernetes platform"
    ]
    assert result.critical_gaps == result.gaps
    assert result.label == "Poor Fit"


def test_network_operations_do_not_hide_advanced_fabric_and_wan_gaps() -> None:
    posting = make_posting(
        title="Senior Network Engineer",
        description=(
            "Required Qualifications\n"
            "Design high-speed Ethernet networks using VLAN, LACP, MLAG, BGP, OSPF, EVPN, and VXLAN.\n"
            "Design and operate InfiniBand networks, including configuration and performance tuning.\n"
            "Strong knowledge of WAN technologies including MPLS, BGP, IPSec, GRE, and SD-WAN."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Maintained InfiniBand fabrics and operated TCP/IP and VLAN infrastructure.",
    )

    assert result.gaps == [
        "No demonstrated BGP, OSPF, EVPN, VXLAN, MLAG, or LACP network-design experience",
        "No demonstrated InfiniBand network design or performance-tuning experience",
        "No demonstrated WAN design experience with MPLS, IPsec, GRE, or SD-WAN",
    ]


def test_specialized_requirements_use_concise_gap_summaries() -> None:
    posting = make_posting(
        title="Forward Deployed GPU Engineer",
        description=(
            "Required Qualifications\n"
            "Lead customer CTO conversations and design partner engagements.\n"
            "Expertise with the GPU & AI Stack."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Linux HPC infrastructure and datacenter operations.",
    )

    assert result.gaps == [
        "No clear r\u00e9sum\u00e9 evidence of at least two years in a formal "
        "customer-facing deployment or technical-delivery role",
        "No demonstrated GPU software-stack experience",
    ]


def test_required_customer_facing_duration_is_not_rewritten_as_executive_work() -> None:
    posting = make_posting(
        title="Forward Deployed Engineer",
        description=(
            "Required Qualifications\n"
            "6+ years in backend, cloud, platform, or SRE roles, including at least "
            "2 years in a customer-facing or deployment technical role.\n"
            "Added bonus\n"
            "Experience with executive design-partner engagements."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Operated Linux HPC infrastructure and datacenter systems.",
    )

    assert (
        "No clear r\u00e9sum\u00e9 evidence of at least two years in a formal "
        "customer-facing deployment or technical-delivery role"
    ) in result.gaps
    assert all("executive-level" not in gap for gap in result.gaps)


def test_infrastructure_support_for_data_pipeline_is_not_data_engineering_gap() -> None:
    posting = make_posting(
        title="Linux Infrastructure Engineer II/III",
        description=(
            "Required Qualifications\n"
            "Experience in Linux system administration.\n"
            "Proven ability to design and implement secure, scalable, and performant "
            "infrastructure to support complex data pipelines and analysis tools."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Designed and operated secure, scalable Linux infrastructure.",
    )

    assert all("data-engineering" not in gap for gap in result.gaps)


def test_security_reliability_instincts_are_not_presented_as_resume_gap() -> None:
    posting = make_posting(
        title="Forward Deployed Engineer",
        description=(
            "Required Qualifications\n"
            "Security & Reliability Instincts: Strong instincts for isolation, "
            "RBAC, uptime, and traceability on customer workloads."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Secured and maintained reliable production infrastructure.",
    )

    assert all("instinct" not in gap.lower() for gap in result.gaps)


def test_hpe_education_heading_excludes_boilerplate_and_incidental_duties() -> None:
    posting = make_posting(
        title="Data Center Lab Administrator / Support Analyst",
        description=(
            "Who We Are\n"
            "We help companies connect and protect data at the speed required "
            "to thrive.\n"
            "Key Responsibilities\n"
            "Ensure coordination with Security to implement all required procedures.\n"
            "Creation of shipping documentation required for certain countries.\n"
            "Education and Experience Required\n"
            "First level university degree or equivalent experience.\n"
            "Work Experience: 2-4 years in a supply chain or operational function.\n"
            "Knowledge and Skills\n"
            "Working knowledge of inventory management and international shipping.\n"
            "Working knowledge of basic IT infrastructure tasks such as server "
            "installation and network cabling.\n"
            "What We Can Offer You\n"
            "Health and wellbeing benefits."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Twenty years of Linux infrastructure and datacenter operations.",
    )

    assert result.requirements_reviewed == [
        "First level university degree or equivalent experience.",
        "Work Experience: 2-4 years in a supply chain or operational function.",
        "Working knowledge of inventory management and international shipping.",
        "Working knowledge of basic IT infrastructure tasks such as server installation and network cabling.",
    ]
    assert all("we help companies" not in gap.lower() for gap in result.gaps)
    assert all("required procedures" not in gap.lower() for gap in result.gaps)
    assert all("certain countries" not in gap.lower() for gap in result.gaps)
    assert any("supply-chain" in gap.lower() for gap in result.gaps)


def test_incidental_required_word_is_not_a_qualification_without_heading() -> None:
    posting = make_posting(
        title="Infrastructure Engineer",
        description=(
            "Coordinate documentation required for international shipping.\n"
            "Linux systems administration experience is required."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Operated enterprise Linux infrastructure.",
    )

    assert result.requirements_reviewed == [
        "Linux systems administration experience is required."
    ]


def test_application_closing_date_after_requirements_is_not_a_resume_gap() -> None:
    posting = make_posting(
        title="Software Linux Engineer",
        description=(
            "What we need to see\n"
            "Linux package management and Python scripting experience.\n"
            "Applications for this job will be accepted at least until July 17, 2026."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Administered Linux package repositories and wrote Python automation.",
    )

    assert all("applications for this job" not in gap.lower() for gap in result.gaps)


def test_centralized_logging_requirement_has_concise_gap_summary() -> None:
    posting = make_posting(
        title="Site Reliability and Observability Engineer",
        description=(
            "Required Qualifications\n"
            "Experience working with centralized logging platforms including "
            "ELK/Elastic Stack, Splunk, CloudWatch, or similar solutions."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Operated Linux infrastructure with Prometheus and Grafana monitoring.",
    )

    assert result.gaps == [
        "No demonstrated centralized-logging platform experience"
    ]


def test_supported_requirements_drive_fit_when_configured_phrases_do_not_overlap() -> None:
    posting = make_posting(
        title="Site Reliability Engineer",
        description=(
            "Requirements\n"
            "Experience with coding and debugging Python.\n"
            "Experience with Linux.\n"
            "Familiarity with Relational Databases & SQL.\n"
            "Sharp analytical and problem-solving skills and a persistent drive "
            "to make things work better.\n"
            "Strong growth mindset and a passion for learning.\n"
            "Strong technical communication skills.\n"
            "Attention to detail.\n"
            "2 years of relevant industry experience.\n"
            "An undergraduate degree or comparable training in a quantitative "
            "field or equivalent, relevant industry experience."
        ),
    )
    resume = (
        "Experience with coding and debugging Python.\n"
        "Experience with Linux infrastructure.\n"
        "Sharp analytical and problem-solving skills and a persistent drive to "
        "make things work better.\n"
        "Strong growth mindset and a passion for learning.\n"
        "Attention to detail.\n"
        "Strong technical communication skills.\n"
        "20 years of relevant industry experience.\n"
        "Comparable training in a quantitative field and equivalent relevant "
        "industry experience."
    )

    result = match_resume_to_posting(posting, make_profile(), resume)

    assert result.label == "Strong"
    assert result.gaps == [
        "No clear résumé evidence of familiarity with Relational Databases & SQL."
    ]
    assert "Linux infrastructure" in result.evidence
    assert "Python scripting and automation" in result.evidence


def test_nvidia_functional_headings_keep_required_and_preferred_work_separate() -> None:
    posting = make_posting(
        title="Software Linux Engineer - Installation and Packaging",
        description=(
            "What we need to see:\n"
            "Bachelor's degree in Computer Science or equivalent experience.\n"
            "4+ years of software development experience, with a strong focus "
            "on Linux system-level development.\n"
            "Skilled in Linux package management tools such as dpkg, RPM, yum, "
            "apt, zypper, or Nix, along with Python or Bash.\n"
            "Experience with packaging standards, repository management, release "
            "automation, and CI/CD workflows.\n"
            "Familiarity with kernel backporting and driver installation (a plus).\n"
            "Ways to stand out from the crowd:\n"
            "Production experience with NixOS and the Nix package manager.\n"
            "Linux kernel driver development and backporting experience."
        ),
    )
    resume = (
        "Twenty years administering Linux infrastructure with apt, yum, and RPM.\n"
        "Built Python and Bash automation plus CI/CD workflows."
    )

    result = match_resume_to_posting(posting, make_profile(), resume)

    assert result.requirements_reviewed == [
        "Bachelor's degree in Computer Science or equivalent experience.",
        "4+ years of software development experience, with a strong focus on "
        "Linux system-level development.",
        "Skilled in Linux package management tools such as dpkg, RPM, yum, apt, "
        "zypper, or Nix, along with Python or Bash.",
        "Experience with packaging standards, repository management, release "
        "automation, and CI/CD workflows.",
    ]
    assert "No clear résumé evidence of 4+ years of professional software development" in result.gaps
    assert (
        "No demonstrated Linux package-development and repository-management experience"
        in result.gaps
    )
    assert all("nixos" not in gap.lower() for gap in result.gaps)
    assert all("kernel" not in gap.lower() for gap in result.gaps)


def test_supported_network_requirements_never_produce_strong_with_no_strengths() -> None:
    posting = make_posting(
        title="Network Engineer II",
        description=(
            "Required Qualifications\n"
            "2+ years technical experience in network design, development, and "
            "automation OR equivalent experience.\n"
            "Other Requirements\n"
            "Ability to pass a background check."
        ),
    )
    resume = (
        "Designed and operated network infrastructure and automated configuration "
        "with Python."
    )

    result = match_resume_to_posting(posting, make_profile(), resume)

    assert result.requirements_reviewed == [
        "2+ years technical experience in network design, development, and "
        "automation OR equivalent experience."
    ]
    assert "network infrastructure and automation" in result.evidence
    assert not (result.label == "Strong" and not result.evidence)


def test_one_supported_requirement_is_not_enough_for_strong_multi_requirement_fit() -> None:
    posting = make_posting(
        title="Network Engineer II",
        description=(
            "Required Qualifications\n"
            "Experience with Linux.\n"
            "Experience operating BGP and EVPN production fabrics."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Operated enterprise Linux infrastructure.",
    )

    assert len(result.requirements_reviewed) == 2
    assert result.supported_requirements == ["Experience with Linux."]
    assert result.label == "Medium"


def test_operational_incident_evidence_supports_combined_on_call_requirement() -> None:
    posting = make_posting(
        title="Senior Platform Engineer",
        description=(
            "Required Qualifications\n"
            "Experience participating in production on-call, incident response, "
            "root-cause analysis, and corrective actions."
        ),
    )
    resume = (
        "Led incident response and root-cause analysis for production "
        "infrastructure and implemented corrective actions."
    )

    result = match_resume_to_posting(posting, make_profile(), resume)

    assert result.supported_requirements == [
        "Experience participating in production on-call, incident response, "
        "root-cause analysis, and corrective actions."
    ]
    assert result.gaps == []


def test_degree_gap_is_not_reported_when_equivalent_experience_is_allowed() -> None:
    posting = make_posting(
        title="Datacenter Engineering Telecom Engineer",
        description=(
            "Required Qualifications\n"
            "Master's Degree in Electrical Engineering, Computer Engineering, "
            "Mechanical Engineering, or related field OR Bachelor's Degree in "
            "Electrical Engineering, Computer Engineering, Mechanical Engineering, "
            "or related field AND 2+ years technical engineering experience OR "
            "equivalent experience."
        ),
    )

    result = match_resume_to_posting(
        posting,
        make_profile(),
        "Twenty years of datacenter infrastructure engineering experience.",
    )

    assert all("bachelor's degree" not in gap.lower() for gap in result.gaps)
