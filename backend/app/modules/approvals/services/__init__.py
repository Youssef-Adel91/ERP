"""
app/modules/approvals/services — Phase 4a Approval Engine Service & Exceptions
"""
from app.modules.approvals.services.approval_engine import (
    assert_document_not_tampered,
    check_and_void_if_modified,
    decide_approval,
    find_matching_rules,
    submit_for_approval,
)
from app.modules.approvals.services.exceptions import (
    ContentHashMismatchError,
    IllegalStateTransitionError,
    SegregationOfDutiesError,
    UnsatisfiableApprovalRuleError,
)

__all__ = [
    "ContentHashMismatchError",
    "IllegalStateTransitionError",
    "SegregationOfDutiesError",
    "UnsatisfiableApprovalRuleError",
    "assert_document_not_tampered",
    "check_and_void_if_modified",
    "decide_approval",
    "find_matching_rules",
    "submit_for_approval",
]
