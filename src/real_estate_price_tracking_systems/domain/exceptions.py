"""Domain exceptions. Callers catch :class:`DomainError` to handle any of them."""


class DomainError(Exception):
    """Base class for errors raised by the domain layer."""


class ConfigNotFoundError(DomainError):
    """No crawler configuration exists for the requested site."""


class ConfigAlreadyExistsError(DomainError):
    """A crawler configuration with the same site id already exists."""


class ConfigCorruptedError(DomainError, ValueError):
    """A stored crawler configuration is invalid or inconsistent."""
