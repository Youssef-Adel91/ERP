"""
app/modules/inventory/exceptions.py — Domain Exceptions for Inventory
"""


class InsufficientStockError(ValueError):
    """Raised when an operation attempts to reserve or consume more stock than is available."""
    pass
