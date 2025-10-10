from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=256)


class UserUpdate(BaseModel):
    full_name: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)
    is_active: bool | None = None
    is_superuser: bool | None = None


class UserRead(UserBase):
    id: str
    is_active: bool
    is_superuser: bool

    class Config:
        from_attributes = True
