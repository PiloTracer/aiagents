from __future__ import annotations

import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from .service import UsersService
from .schemas import UserCreate
from .repository import UsersRepository


logger = logging.getLogger(__name__)


def ensure_default_admin(db: Session) -> None:
    try:
        print("[bootstrap] ensure_default_admin: starting")
    except Exception:
        pass

    # Sanity check: ensure users table exists
    try:
        db.execute(text("SELECT 1 FROM users LIMIT 1"))
    except Exception as e:
        try:
            print(f"[bootstrap] users table not ready yet: {e}")
        except Exception:
            pass
        db.rollback()
        return
    email = settings.ADMIN_EMAIL
    password = settings.ADMIN_PASSWORD
    if not email or not password:
        try:
            print("[bootstrap] ADMIN_EMAIL or ADMIN_PASSWORD not set; skipping admin bootstrap")
        except Exception:
            pass
        return

    repo = UsersRepository(db)
    existing = repo.get_by_email(email)
    svc = UsersService(db)
    if existing:
        try:
            print(f"[bootstrap] Found existing admin email {email}; ensuring privileges and activation")
        except Exception:
            pass
        # Ensure admin account has correct flags and password
        updated = False
        if not existing.is_superuser:
            existing.is_superuser = True
            updated = True
        if not existing.is_active:
            existing.is_active = True
            updated = True
        if password:
            # Reset password to env-provided value
            from app.core.security import get_password_hash

            existing.hashed_password = get_password_hash(password)
            updated = True
        if updated:
            db.add(existing)
            db.commit()
            db.refresh(existing)
            try:
                print(f"[bootstrap] Default admin '{existing.email}' updated (active={existing.is_active}, superuser={existing.is_superuser})")
            except Exception:
                pass
        return

    try:
        try:
            user = svc.register_user(
                UserCreate(email=email, password=password, full_name=settings.ADMIN_FULL_NAME),
                is_superuser=True,
            )
            try:
                print(f"[bootstrap] Default admin '{user.email}' created")
            except Exception:
                pass
        except Exception as exc:
            db.rollback()
            try:
                print(f"[bootstrap] Failed to create default admin: {exc}")
            except Exception:
                pass
            return
    except IntegrityError:
        db.rollback()
        return
    except ValueError:
        return
