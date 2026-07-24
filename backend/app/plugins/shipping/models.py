"""app/plugins/shipping/models.py — Shipping Plugin Models (Stub)

Future models:
  - ShipmentOrder: Tracks a delivery from warehouse to customer
  - Carrier: Bosta, J&T Express, Aramex, etc.
  - TrackingEvent: Status updates from carrier webhooks
  - CODCollection: Cash collected on delivery (feeds into COD Risk Assessment)
"""
# These models will be implemented in a future sprint.
# They will emit "cod.collected" and "cod.rejected" events to the EventBus,
# which will update Contact.cod_risk_score and ContactRelationship.cod_rejection_rate.
