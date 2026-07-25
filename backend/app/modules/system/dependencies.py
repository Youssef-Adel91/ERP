"""
app/modules/system/dependencies.py — Auth Dependencies for FastAPI Routes
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_public_db
from app.core.security import decode_token
from app.modules.system.models import User, UserRole


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_public_db),
) -> User:
    """
    Resolve the authenticated user from request.state (set by TenantMiddleware).

    Raises 401 if no user context, 403 if account is inactive.
    """
    user_id_str: str | None = getattr(request.state, "current_user_id", None)
    tenant_id_str: str | None = getattr(request.state, "tenant_id", None)

    if not user_id_str or not tenant_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(
        select(User).where(User.id == UUID(user_id_str))
    )
    user: User | None = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated.",
        )

    return user


# Annotated shorthand — use as `current_user: CurrentUser` in route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    """
    Dependency factory for role-based access control.

    Usage:
        @router.post("/", dependencies=[Depends(require_roles("admin", "accountant"))])
        async def create_entry(...): ...
    """
    async def _check_roles(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {list(roles)}.",
            )
        return current_user

    return Depends(_check_roles)
