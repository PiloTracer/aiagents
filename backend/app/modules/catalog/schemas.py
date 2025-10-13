from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


# ---- Area Schemas ----


class AreaBase(BaseModel):
    name: str = Field(..., max_length=150)
    description: str | None = Field(None, max_length=10_000)
    vector_collection: str | None = Field(None, max_length=150)
    access_level: str = Field(default="restricted", max_length=50)
    is_active: bool = True


class AreaCreate(AreaBase):
    slug: str = Field(..., max_length=100)


class AreaUpdate(BaseModel):
    name: str | None = Field(None, max_length=150)
    description: str | None = Field(None, max_length=10_000)
    vector_collection: str | None = Field(None, max_length=150)
    access_level: str | None = Field(None, max_length=50)
    is_active: bool | None = None


class AreaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    description: str | None
    vector_collection: str
    access_level: str
    is_active: bool
    created_at: datetime
    updated_at: datetime | None
    agent_slugs: list[str] = []


# ---- Agent Schemas ----


class AgentBase(BaseModel):
    display_name: str = Field(..., max_length=150)
    description: str | None = Field(None, max_length=10_000)
    agent_type: str = Field(..., max_length=50)
    capabilities: dict[str, Any] | None = None
    resource_permissions: dict[str, Any] = Field(default_factory=dict)
    system_prompt: str
    temperature: float = 0.2
    max_tokens: int = 2048
    is_active: bool = True
    execution_order: int = 0
    fallback_agent_slug: str | None = Field(default=None, max_length=100)
    area_slugs: list[str] = Field(default_factory=list)
    role_slugs: list[str] = Field(default_factory=list)


class AgentCreate(AgentBase):
    slug: str = Field(..., max_length=100)


class AgentUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=150)
    description: str | None = Field(None, max_length=10_000)
    agent_type: str | None = Field(None, max_length=50)
    capabilities: dict[str, Any] | None = None
    resource_permissions: dict[str, Any] | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    is_active: bool | None = None
    execution_order: int | None = None
    fallback_agent_slug: str | None = Field(default=None, max_length=100)
    area_slugs: list[str] | None = None
    role_slugs: list[str] | None = None


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    display_name: str
    description: str | None
    agent_type: str
    capabilities: dict[str, Any] | None
    resource_permissions: dict[str, Any]
    system_prompt: str
    temperature: float
    max_tokens: int
    is_active: bool
    execution_order: int
    fallback_agent_id: str | None
    fallback_agent_slug: str | None
    created_at: datetime
    updated_at: datetime | None
    area_slugs: list[str]
    role_slugs: list[str]


# ---- Role Schemas ----


class RoleBase(BaseModel):
    description: str | None = Field(None, max_length=10_000)
    permissions: dict[str, Any] | None = None
    level: int = 0
    is_system_role: bool = False
    inherits_from_slug: str | None = Field(default=None, max_length=100)
    agent_slugs: list[str] = Field(default_factory=list)


class RoleCreate(RoleBase):
    name: str = Field(..., max_length=150)
    slug: str | None = Field(default=None, max_length=100)


class RoleUpdate(BaseModel):
    name: str | None = Field(None, max_length=150)
    description: str | None = Field(None, max_length=10_000)
    permissions: dict[str, Any] | None = None
    level: int | None = None
    is_system_role: bool | None = None
    inherits_from_slug: str | None = Field(default=None, max_length=100)
    agent_slugs: list[str] | None = None


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    description: str | None
    permissions: dict[str, Any] | None
    level: int
    is_system_role: bool
    inherits_from_id: str | None
    inherits_from_slug: str | None
    created_at: datetime
    updated_at: datetime | None
    agent_slugs: list[str]


# ---- User Role Assignment ----


class UserRoleAssignmentRequest(BaseModel):
    role_slugs: list[str] = Field(default_factory=list)

