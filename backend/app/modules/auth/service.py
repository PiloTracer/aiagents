from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.modules.users.service import UsersService


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UsersService(db)

    def login(self, email: str, password: str) -> str | None:
        user = self.users.authenticate(email, password)
        if not user or not user.is_active:
            return None
        return create_access_token(subject=user.id)

