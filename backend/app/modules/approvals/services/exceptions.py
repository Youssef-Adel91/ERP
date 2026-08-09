"""
app/modules/approvals/services/exceptions.py — Domain Exceptions for Approvals (Phase 4a)
"""


class SegregationOfDutiesError(ValueError):
    """
    Raised when an approver attempts to approve their own document (FR-1206).
    The creator of a document can NEVER approve their own document, regardless of role.
    """


class ContentHashMismatchError(ValueError):
    """
    Raised when document content has been modified after approval (FR-1212).
    Modifying an approved document in DRAFT state instantly voids the prior approval.
    """


class IllegalStateTransitionError(ValueError):
    """
    Raised when an invalid state transition is attempted on a document lifecycle (FR-1202).
    """


class UnsatisfiableApprovalRuleError(ValueError):
    """
    Raised when an approval rule configuration is unsatisfiable (e.g., self-approval in single user tenant).
    """
