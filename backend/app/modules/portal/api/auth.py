"""
app/modules/portal/api/auth.py — Client Portal Authentication

Two-step OTP login:
  1. POST /portal/auth/login         — looks up the Contact by phone, issues
     a real 6-digit OTP (Redis-backed, single-use, 5 min TTL — see
     app.core.security.security.create_portal_otp) and delivers it via the
     tenant's WhatsApp integration, falling back to email (same multi
     -channel dispatcher used elsewhere in the app — see
     app.core.notifications.dispatch.notify_contact). No token is issued
     at this step.
  2. POST /portal/auth/login/verify  — verifies the submitted code against
     Redis (app.core.security.security.verify_portal_otp) and, only on a
     match, issues the scoped portal JWT.

Tenant isolation: `/api/v1/portal/*` is a bypass path for TenantMiddleware
(see app.core.db.database._BYPASS_PREFIXES — the portal manages its own
auth, so there's no JWT for the middleware to resolve a tenant from yet),
so this module resolves its own tenant DB access via
app.core.db.database.tenant_session(), the same schema_translate_map
-based mechanism every other tenant-scoped session in this codebase uses
— NOT a manual `SET search_path` (which previously also had a naming bug:
it stripped dashes entirely instead of matching app.core.db.context.
schema_for()'s `tenant_<uuid-with-underscores>` convention, so it was
pointing at a schema that didn't exist).
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID

import redis.asyncio as aioredis
from jose import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import settings
from app.core.db.database import get_redis, public_session, tenant_session
from app.core.notifications.dispatch import notify_contact
from app.core.security.security import create_portal_otp, verify_portal_otp
from app.modules.contacts.models import Contact

router = APIRouter(prefix="/portal/auth", tags=["Portal Auth"])


class LoginRequest(BaseModel):
    phone_e164: str
    tenant_id: UUID


class VerifyOtpRequest(BaseModel):
    phone_e164: str
    tenant_id: UUID
    otp_code: str


class MessageResponse(BaseModel):
    message: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PortalContactData(BaseModel):
    contact_id: UUID
    tenant_id: UUID


def create_portal_token(contact_id: UUID, tenant_id: UUID) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(hours=24)
    payload = {
        "sub": str(contact_id),
        "tenant_id": str(tenant_id),
        "type": "portal_access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


async def _find_contact_by_phone(tenant_id: UUID, phone_e164: str) -> Contact | None:
    """Looks up the Contact by phone within the tenant's own schema."""
    try:
        async with tenant_session(tenant_id) as session:
            result = await session.execute(
                select(Contact).where(Contact.phone_e164 == phone_e164)
            )
            return result.scalar_one_or_none()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Tenant ID") from exc


@router.post("/login", response_model=MessageResponse)
async def login_portal(
    data: LoginRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Step 1 of Client Portal login: looks up the Contact by phone number
    and, if found, generates a real OTP and delivers it via WhatsApp
    (falling back to email) — see module docstring. Never returns an
    access token; call /portal/auth/login/verify with the received code
    to actually authenticate.
    """
    contact = await _find_contact_by_phone(data.tenant_id, data.phone_e164)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contact not found for this phone number.",
        )

    otp_code = await create_portal_otp(data.tenant_id, contact.id, redis)

    async with public_session() as public_db:
        channel = await notify_contact(
            public_session=public_db,
            tenant_id=data.tenant_id,
            contact=contact,
            whatsapp_template="portal_otp_code",
            whatsapp_parameters=[{"type": "text", "text": otp_code}],
            email_subject="رمز الدخول لبوابة العملاء — Omni ERP",
            email_body_text=(
                f"رمز الدخول لبوابة العملاء الخاص بك هو: {otp_code}\n\n"
                "هذا الرمز صالح لمدة 5 دقائق فقط.\n"
                "إذا لم تطلب هذا الرمز، يمكنك تجاهل هذه الرسالة بأمان.\n\n"
                f"Your Client Portal login code is: {otp_code}\n"
                "This code is valid for 5 minutes only."
            ),
            email_body_html=(
                f"<p>رمز الدخول لبوابة العملاء الخاص بك هو: <b>{otp_code}</b></p>"
                "<p>هذا الرمز صالح لمدة 5 دقائق فقط.</p>"
                f"<p>Your Client Portal login code is: <b>{otp_code}</b></p>"
            ),
        )

    if channel == "none":
        # Contact has no reachable phone/email, or both channels failed —
        # do not leave the caller thinking a code is on its way.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not deliver the login code via WhatsApp or email.",
        )

    return MessageResponse(message="A login code has been sent.")


@router.post("/login/verify", response_model=TokenResponse)
async def verify_portal_login(
    data: VerifyOtpRequest,
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Step 2 of Client Portal login: verifies the OTP issued by /login
    (single-use, 5 min TTL, bounded attempts — see
    app.core.security.security.verify_portal_otp) and, only on a match,
    issues a tightly scoped token granting read access ONLY to this
    contact_id.
    """
    contact = await _find_contact_by_phone(data.tenant_id, data.phone_e164)
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contact not found for this phone number.",
        )

    is_valid = await verify_portal_otp(data.tenant_id, contact.id, data.otp_code, redis)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired login code.",
        )

    token = create_portal_token(contact.id, data.tenant_id)
    return TokenResponse(access_token=token)


# Reusable Dependency for protecting Portal endpoints
portal_oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/portal/auth/login/verify")


async def get_portal_contact(
    token: str = Depends(portal_oauth2_scheme),
) -> PortalContactData:
    """
    Decodes the portal token and enforces RBAC (preventing ERP users from
    using the portal, and portal users from using the ERP). Does not touch
    the database — endpoints that need tenant-scoped data should open
    their own `tenant_session(portal_user.tenant_id)` (see module
    docstring for why `/api/v1/portal/*` can't rely on the standard
    get_tenant_db()/request.state.tenant_id path).
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "portal_access":
            raise HTTPException(status_code=403, detail="Invalid token type for Portal.")

        contact_id = UUID(payload["sub"])
        tenant_id = UUID(payload["tenant_id"])

        return PortalContactData(contact_id=contact_id, tenant_id=tenant_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
        )
