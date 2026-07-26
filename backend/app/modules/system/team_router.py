"""
app/modules/system/team_router.py — Team Management API

Responsible for creating and listing users within a single tenant.
Only accessible to users with the OWNER role.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_public_db
from app.core.security import RequireRole, hash_password
from app.modules.system.dependencies import CurrentUser
from app.modules.system.models import User, UserRole
from app.modules.system.schemas import UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Schemas ───────────────────────────────────────────────────────────────────

class TeamMemberCreateRequest(BaseModel):
    """Payload for creating a new team member."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=255)
    role: UserRole


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=list[UserResponse],
    summary="List all team members",
    tags=["Team Management"],
)
async def list_team_members(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_public_db),
) -> list[UserResponse]:
    """
    Returns all users belonging to the current tenant.
    Any authenticated user can list the team.
    """
    result = await db.execute(
        select(User).where(User.tenant_id == current_user.tenant_id),
    )
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new team member",
    dependencies=[Depends(RequireRole(["OWNER"]))],
    tags=["Team Management"],
)
async def create_team_member(
    data: TeamMemberCreateRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_public_db),
) -> UserResponse:
    """
    Create a new user account under the current tenant.
    Only the OWNER can perform this action.
    """
    # 1. Check if email exists globally (since users are in public schema)
    existing = await db.execute(
        select(User).where(User.email == data.email.lower()),
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{data.email}' is already in use.",
        )

    # 2. Create the user
    new_user = User(
        tenant_id=current_user.tenant_id,
        email=data.email.lower(),
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return UserResponse.model_validate(new_user)
