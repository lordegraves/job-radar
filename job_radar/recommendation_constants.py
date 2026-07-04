"""Shared recommendation vocabulary for Job Radar.

These constants keep report, email, scoring, and history logic from drifting
when user-facing action labels or business-rule risk labels change.
"""

ACTION_APPLY = "Apply"
ACTION_APPLY_WITH_RECRUITER = "Apply + Recruiter Message"
ACTION_NETWORK_FIRST = "Network First"
ACTION_TAILOR_RESUME = "Tailor Resume"
ACTION_TRACK_STATUS = "Track Status"
ACTION_PREVIOUSLY_REVIEWED = "Previously Reviewed"
ACTION_HOLD = "Hold"
ACTION_PASS = "Pass"

RECOMMENDATION_SUMMARY_ORDER = [
    ACTION_APPLY,
    ACTION_APPLY_WITH_RECRUITER,
    ACTION_NETWORK_FIRST,
    ACTION_TAILOR_RESUME,
    ACTION_TRACK_STATUS,
    ACTION_PREVIOUSLY_REVIEWED,
    ACTION_HOLD,
    ACTION_PASS,
]

TRACK_STATUS_ALREADY_APPLIED_MESSAGE = (
    "You already applied for this job. Track the existing application instead of applying again."
)

RISK_BELOW_COMPENSATION_FLOOR = "below compensation floor"
RISK_HARD_LOCATION_MISMATCH = "hard location mismatch"
RISK_ROLE_FAMILY_MISMATCH = "role family mismatch"
RISK_SUPPORT_ROLE = "support role"
RISK_HIGH_COMPETITION_EMPLOYER = "high competition employer"
RISK_SOFTWARE_HEAVY_TRANSLATION = "software-heavy translation risk"
RISK_SECURITY_DOMAIN_TRANSLATION = "security-domain translation risk"
RISK_PRODUCTION_KUBERNETES_TRANSLATION = "production Kubernetes translation risk"
RISK_GENERIC_REMOTE_COMPETITION = "generic remote competition"
RISK_LOCATION_NEEDS_CONFIRMATION = "location needs confirmation"
RISK_NOT_LOCATION_ELIGIBLE = "not location eligible"
RISK_LEADERSHIP_AMBIGUITY = "leadership ambiguity risk"

HISTORY_ALREADY_APPLIED = "already_applied"
HISTORY_PRIOR_NO_INTERVIEW_DESPITE_STRONG_MATCH = "prior_no_interview_despite_strong_match"
HISTORY_PRIOR_NO_INTERVIEW = "prior_no_interview"
HISTORY_PRIOR_REJECTED = "prior_rejected"
HISTORY_PRIOR_SIMILAR_ROLE = "prior_similar_role"
HISTORY_PRIOR_SKIPPED_SIMILAR_ROLE = "prior_skipped_similar_role"
