"""Session auth middleware for FastAPI."""
from fastapi import Depends, HTTPException, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from typing import Optional
from app.db.base import get_db
from app.models import Session, User


async def get_current_user(
    nexus_session: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not nexus_session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(
        select(Session).where(
            Session.token == nexus_session,
            Session.active == True,
            Session.expires_at > datetime.now(timezone.utc),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    user = await db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="User inactive")

    # Attach tenant_id to user object for convenience
    user.tenant_id = session.tenant_id
    return user
