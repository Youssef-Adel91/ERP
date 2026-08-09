"""
app/modules/portal/services/payments.py — Payment Intent Engine (Portal)
"""
from uuid import UUID
from pydantic import BaseModel

class PaymentIntentResponse(BaseModel):
    intent_id: str
    checkout_url: str
    amount: float
    currency: str

async def generate_payment_intent(invoice_id: UUID, contact_id: UUID, amount: float, currency: str) -> PaymentIntentResponse:
    """
    Structurally prepares the system for a future Paymob/Fawry integration.
    Generates a mock 'Payment Intent' record and returns a fake checkout URL.
    """
    mock_intent_id = f"pi_{str(invoice_id)[:8]}"
    
    # In production, this would make an S2S call to Paymob/Fawry API to generate an Iframe URL
    # and save the intent to a `PaymentIntents` DB table mapped to this invoice.
    
    return PaymentIntentResponse(
        intent_id=mock_intent_id,
        checkout_url=f"https://checkout.paymob.mock/pay/{mock_intent_id}",
        amount=amount,
        currency=currency
    )
