"""
app.modules.eta.exceptions — Custom Exceptions for ETA Compliance Module
"""
from __future__ import annotations


class EtaException(Exception):
    """Base exception for Egyptian Tax Authority (ETA) module."""
    pass


class EtaRateDeferredError(EtaException):
    """
    Raised when the Global Rate Governor throttles a call (F-1, FR-540)
    or when ETA returns HTTP 429 Too Many Requests (FR-542).
    Causes the document state machine to transition to `RATE_DEFERRED` and requeue.
    """
    pass


class EtaAuthenticationError(EtaException):
    """
    Raised when acquiring or refreshing an ETA OAuth token fails (F-3).
    """
    pass


class EtaServiceUnavailableError(EtaException):
    """
    Raised when ETA returns HTTP 503 or is unreachable.
    """
    pass


class EtaMissingItemCodeError(EtaException):
    """
    Raised when an invoice line item lacks a valid EGS/GS1 item code (FR-521).
    Prevents document submission and alerts the merchant before an ETA rejection.
    """
    pass


class EtaTimeoutError(EtaException):
    """
    Raised when an HTTP request to ETA API times out.
    Triggers F-4 external idempotency handling (SUBMIT_UNCERTAIN state).
    """
    pass


class EtaSubmissionTimeoutError(EtaException):
    """
    Raised when batch submission times out (F-4).
    Documents are transitioned to SUBMIT_UNCERTAIN and must be verified before retrying.
    """
    pass
