from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
import logging
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from .schemas import UserCreate, UserRead
from .service import UsersService
from .models import User


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(data: UserCreate, db: Annotated[Session, Depends(get_db)]):
    svc = UsersService(db)
    try:
        logger.info("Registering user %s", data.email)
        user = svc.register_user(data)
    except ValueError as e:
        logger.info("Registration failed for %s: %s", data.email, e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.info("User %s registered with id %s", user.email, user.id)
    return user


@router.get("/me", response_model=UserRead)
def read_me(current: Annotated[User, Depends(get_current_user)]):
    return current



