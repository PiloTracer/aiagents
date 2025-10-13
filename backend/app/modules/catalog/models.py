from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

try:  # Prefer JSONB on PostgreSQL but gracefully fallback
    from sqlalchemy.dialects.postgresql import JSONB
except Exception:  # pragma: no cover - fallback for non-PG environments
    from sqlalchemy import JSON as JSONB  # type: ignore


class Area(Base):
    __tablename__ = "areas"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    vector_collection: Mapped[str] = mapped_column(String(150))
    access_level: Mapped[str] = mapped_column(String(50), default="restricted")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    agent_links: Mapped[list["AgentArea"]] = relationship(
        "AgentArea",
        back_populates="area",
        cascade="all, delete-orphan",
        overlaps="agents",
    )
    agents: Mapped[list["Agent"]] = relationship(
        "Agent",
        secondary="agent_areas",
        back_populates="areas",
        viewonly=True,
        overlaps="agent_links,area_links",
    )


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    agent_type: Mapped[str] = mapped_column(String(50))
    capabilities: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    resource_permissions: Mapped[dict] = mapped_column(JSONB, default=dict)
    system_prompt: Mapped[str] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    execution_order: Mapped[int] = mapped_column(Integer, default=0)
    fallback_agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    fallback_agent: Mapped["Agent | None"] = relationship(
        "Agent", remote_side="Agent.id", lazy="joined"
    )
    area_links: Mapped[list["AgentArea"]] = relationship(
        "AgentArea",
        back_populates="agent",
        cascade="all, delete-orphan",
        overlaps="areas",
    )
    areas: Mapped[list["Area"]] = relationship(
        "Area",
        secondary="agent_areas",
        back_populates="agents",
        viewonly=True,
        overlaps="agent_links,area_links",
    )
    role_links: Mapped[list["RoleAgent"]] = relationship(
        "RoleAgent",
        back_populates="agent",
        cascade="all, delete-orphan",
        overlaps="roles",
    )
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary="role_agents",
        back_populates="agents",
        viewonly=True,
        overlaps="role_links,agents",
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    permissions: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    level: Mapped[int] = mapped_column(Integer, default=0)
    is_system_role: Mapped[bool] = mapped_column(Boolean, default=False)
    inherits_from_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    inherits_from: Mapped["Role | None"] = relationship(
        "Role", remote_side="Role.id", lazy="joined"
    )
    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="role",
        cascade="all, delete-orphan",
        overlaps="agents",
    )
    role_agents: Mapped[list["RoleAgent"]] = relationship(
        "RoleAgent",
        back_populates="role",
        cascade="all, delete-orphan",
        overlaps="agents,roles",
    )
    agents: Mapped[list["Agent"]] = relationship(
        "Agent",
        secondary="role_agents",
        back_populates="roles",
        viewonly=True,
        overlaps="role_links,roles",
    )


class AgentArea(Base):
    __tablename__ = "agent_areas"
    __table_args__ = (
        UniqueConstraint("agent_id", "area_id", name="uq_agent_area"),
    )

    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    area_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("areas.id", ondelete="CASCADE"), primary_key=True
    )
    access_level: Mapped[str] = mapped_column(String(50), default="read")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="area_links",
        overlaps="areas,agents",
    )
    area: Mapped["Area"] = relationship(
        "Area",
        back_populates="agent_links",
        overlaps="areas,agents",
    )


class RoleAgent(Base):
    __tablename__ = "role_agents"
    __table_args__ = (
        UniqueConstraint("role_id", "agent_id", name="uq_role_agent"),
    )

    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    role: Mapped["Role"] = relationship(
        "Role",
        back_populates="role_agents",
        overlaps="roles,agents",
    )
    agent: Mapped["Agent"] = relationship(
        "Agent",
        back_populates="role_links",
        overlaps="roles,agents",
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")
