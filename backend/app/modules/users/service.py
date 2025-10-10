from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import get_password_hash, verify_password
from .models import User
from .schemas import UserCreate, UserUpdate
from .repository import UsersRepository


class UsersService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = UsersRepository(db)

    def register_user(self, data: UserCreate, is_superuser: bool = False) -> User:
        existing = self.repo.get_by_email(data.email)
        if existing:
            raise ValueError("Email already registered")
        user = User(
            email=data.email,
            full_name=data.full_name,
            hashed_password=get_password_hash(data.password),
            is_active=True if is_superuser else False,
            is_superuser=is_superuser,
        )
        return self.repo.create(user)

    def authenticate(self, email: str, password: str) -> User | None:
        user = self.repo.get_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
