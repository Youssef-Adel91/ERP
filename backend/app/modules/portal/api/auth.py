"""
app/modules/portal/api/auth.py — Client Portal Authentication
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID
from jose import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db.database import get_tenant_db as get_db_session
from app.modules.contacts.models import Contact

router = APIRouter(prefix="/portal/auth", tags=["Portal Auth"])

class LoginRequest(BaseModel):
    phone_e164: str
    tenant_id: UUID

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

@router.post("/login", response_model=TokenResponse)
async def login_portal(
    data: LoginRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Mock OTP login for Client Portal.
    In production, this would send an SMS/WhatsApp OTP and verify it.
    """
    tenant_schema = f"tenant_{str(data.tenant_id).replace('-', '')}"
    try:
        await session.execute(f"SET search_path TO {tenant_schema}")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Tenant ID")

    result = await session.execute(
        select(Contact).where(Contact.phone_e164 == data.phone_e164)
    )
    contact = result.scalar_one_or_none()

    if not contact:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Contact not found for this phone number."
        )

    # Issue a tightly scoped token granting read access ONLY to this contact_id
    token = create_portal_token(contact.id, data.tenant_id)
    return TokenResponse(access_token=token)

# Reusable Dependency for protecting Portal endpoints
portal_oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/portal/auth/login")

async def get_portal_contact(
    token: str = Depends(portal_oauth2_scheme),
    session: AsyncSession = Depends(get_db_session)
) -> PortalContactData:
    """
    Decodes the portal token, enforces RBAC (preventing ERP users from using portal, 
    and portal users from using ERP), and switches the database schema.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        if payload.get("type") != "portal_access":
            raise HTTPException(status_code=403, detail="Invalid token type for Portal.")
            
        contact_id = UUID(payload["sub"])
        tenant_id = UUID(payload["tenant_id"])
        
        tenant_schema = f"tenant_{str(tenant_id).replace('-', '')}"
        await session.execute(f"SET search_path TO {tenant_schema}")
        
        return PortalContactData(contact_id=contact_id, tenant_id=tenant_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Could not validate credentials."
        )
