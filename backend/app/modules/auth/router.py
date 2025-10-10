from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.modules.users.models import User
from .schemas import LoginRequest, TokenResponse
from .service import AuthService


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]):
    svc = AuthService(db)
    token = svc.login(payload.email, payload.password)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=token)


@router.get("/me", response_model=dict)
def me(current: Annotated[User, Depends(get_current_user)]):
    return {"id": current.id, "email": current.email, "full_name": current.full_name, "is_superuser": current.is_superuser}

