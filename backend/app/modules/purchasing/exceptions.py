"""app/modules/purchasing/exceptions.py — Domain Exceptions for Purchasing Module"""
from __future__ import annotations

from uuid import UUID


class OverReceiptError(Exception):
    """
    Raised when qty_received > qty_ordered on a PurchaseOrderLine (FR-522).
    Enforces strict Bounded Context 0% tolerance invariant.
    """

    def __init__(
        self,
        po_line_id: UUID,
        qty_ordered: str,
        current_received: str,
        attempted_receipt: str,
        message: str | None = None,
    ):
        self.po_line_id = po_line_id
        self.qty_ordered = qty_ordered
        self.current_received = current_received
        self.attempted_receipt = attempted_receipt
        super().__init__(
            message
            or f"OverReceiptError: PO Line {po_line_id} ordered {qty_ordered}, already received {current_received}, "
            f"cannot receive additional {attempted_receipt} (exceeds ordered quantity)."
        )


class PurchaseOrderNotFoundError(Exception):
    """Raised when a PurchaseOrder cannot be found by ID or Number."""

    def __init__(self, po_id: UUID | str):
        self.po_id = po_id
        super().__init__(f"PurchaseOrder not found: {po_id}")


class SupplierNotFoundError(Exception):
    """
    Raised when a PurchaseOrder/GoodsReceipt/VendorBill references a
    `supplier_id` that doesn't resolve to a SUPPLIER-type Contact in the
    tenant's `contacts` table. `supplier_id` is a bare UUID column (no DB
    foreign key to `tenant.contacts.id`), so this validated lookup is the
    referential-integrity check that would otherwise be missing entirely.
    """

    def __init__(self, supplier_id: UUID | str):
        self.supplier_id = supplier_id
        super().__init__(
            f"Supplier '{supplier_id}' not found — no contact with this ID and "
            f"contact_type='supplier' exists in this tenant."
        )


class PurchaseOrderLineNotFoundError(Exception):
    """Raised when a PurchaseOrderLine cannot be found."""

    def __init__(self, po_line_id: UUID | str):
        self.po_line_id = po_line_id
        super().__init__(f"PurchaseOrderLine not found: {po_line_id}")


class InvalidPOStateError(Exception):
    """Raised when an operation is invalid in the current PO lifecycle state."""

    def __init__(self, po_id: UUID, current_state: str, action: str):
        self.po_id = po_id
        self.current_state = current_state
        self.action = action
        super().__init__(
            f"Cannot perform '{action}' on PurchaseOrder {po_id} in state '{current_state}'."
        )


class ThreeWayMatchError(Exception):
    """
    Raised when a VendorBill fails Three-Way Match (FR-521, FR-527) due to qty or price variance
    exceeding tolerance (0% tolerance currently enforced).
    """

    def __init__(
        self,
        bill_id: UUID,
        bill_line_id: UUID,
        qty_variance: str,
        price_variance: str,
        message: str | None = None,
    ):
        self.bill_id = bill_id
        self.bill_line_id = bill_line_id
        self.qty_variance = qty_variance
        self.price_variance = price_variance
        super().__init__(
            message
            or f"ThreeWayMatchError: Bill Line {bill_line_id} failed match with qty variance {qty_variance} "
            f"and price variance {price_variance}."
        )


class VendorBillNotFoundError(Exception):
    """Raised when a VendorBill cannot be found by ID."""

    def __init__(self, bill_id: UUID | str):
        self.bill_id = bill_id
        super().__init__(f"VendorBill not found: {bill_id}")


class ImportShipmentNotFoundError(Exception):
    """Raised when an ImportShipment cannot be found by ID or Reference."""

    def __init__(self, shipment_id: UUID | str):
        self.shipment_id = shipment_id
        super().__init__(f"ImportShipment not found: {shipment_id}")


class LandedCostAllocationError(Exception):
    """Raised when Landed Cost allocation math drifts or targets are missing."""

    def __init__(self, message: str):
        super().__init__(message)


class SupplierPaymentNotFoundError(Exception):
    """Raised when a SupplierPayment cannot be found by ID."""

    def __init__(self, payment_id: UUID | str):
        self.payment_id = payment_id
        super().__init__(f"SupplierPayment not found: {payment_id}")


class PaymentAllocationError(Exception):
    """Raised when payment allocation fails validation or business rules."""

    def __init__(self, message: str):
        super().__init__(message)
