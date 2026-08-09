"""
app/plugins/whatsapp/router.py — WhatsApp Plugin Router Registry
"""
"""
app/plugins/whatsapp/router.py — WhatsApp Plugin Router Registry

Only the Meta webhook receiver lives here — it's mounted at bare root (no
/api/v1 prefix, no auth) in main.py since Meta calls one fixed external
URL. The tenant-facing config CRUD (api/config.py) is a normal
authenticated API surface and is mounted separately, under the standard
/api/v1 prefix, directly in main.py — see the "WhatsApp Integration"
registration step.
"""
from fastapi import APIRouter
from app.plugins.whatsapp.api.webhooks import router as webhooks_router

router = APIRouter()
router.include_router(webhooks_router)
