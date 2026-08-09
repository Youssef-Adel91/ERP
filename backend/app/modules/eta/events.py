"""
app.modules.eta.events — ETA module event consumers registration
"""
from app.modules.eta.services.translation import register_eta_event_consumers

# Automatically register event consumers when module is imported
register_eta_event_consumers()
