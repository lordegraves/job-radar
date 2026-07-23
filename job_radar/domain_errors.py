"""Define safe domain failures for company and Administration operations."""


class JuniorDomainError(RuntimeError):
    """Base class for expected business-rule failures."""


class NoActiveProfileError(JuniorDomainError):
    """Raised when an operation requires an active managed profile."""


class EmployerNotFoundError(JuniorDomainError):
    """Raised when the requested employer does not exist."""


class EmployerNotAssignedError(JuniorDomainError):
    """Raised when an employer is outside the requested profile."""


class EmployerAlreadyAssignedError(JuniorDomainError):
    """Raised when a profile already owns the requested assignment."""


class EmployerUnavailableError(JuniorDomainError):
    """Raised when a global employer cannot currently be assigned or scanned."""


class EmployerConfigurationError(JuniorDomainError):
    """Raised when an employer source is incomplete or invalid."""


class EmployerInUseError(JuniorDomainError):
    """Raised when references prevent a destructive employer operation."""


class InvalidCompanyStateError(JuniorDomainError):
    """Raised when a requested company state transition is invalid."""


class AdminAccessRequiredError(JuniorDomainError):
    """Raised when a service requires explicitly unlocked Administration."""


class RecommendationNotFoundError(JuniorDomainError):
    """Raised when a requested profile recommendation does not exist."""
