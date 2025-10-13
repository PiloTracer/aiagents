from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.users.models import User
from .models import (
    Agent,
    AgentArea,
    Area,
    Role,
    RoleAgent,
    UserRole,
)


class CatalogRepository:
    def __init__(self, db: Session):
        self.db = db

    # ---- Areas ----
    def list_areas(self) -> list[Area]:
        stmt = (
            select(Area)
            .options(
                selectinload(Area.agents),
            )
            .order_by(Area.slug)
        )
        return list(self.db.scalars(stmt))

    def get_area_by_slug(self, slug: str) -> Area | None:
        stmt = select(Area).where(Area.slug == slug)
        return self.db.scalar(stmt)

    def get_area_by_id(self, area_id: str) -> Area | None:
        return self.db.get(Area, area_id)

    def get_areas_by_slugs(self, slugs: Sequence[str]) -> list[Area]:
        if not slugs:
            return []
        stmt = select(Area).where(Area.slug.in_(slugs))
        return list(self.db.scalars(stmt))

    def add_area(self, area: Area) -> Area:
        self.db.add(area)
        self.db.commit()
        self.db.refresh(area)
        return area

    # ---- Agents ----
    def list_agents(self) -> list[Agent]:
        stmt = (
            select(Agent)
            .options(
                selectinload(Agent.areas),
                selectinload(Agent.roles),
                selectinload(Agent.fallback_agent),
            )
            .order_by(Agent.execution_order, Agent.slug)
        )
        return list(self.db.scalars(stmt))

    def get_agent_by_slug(self, slug: str) -> Agent | None:
        stmt = (
            select(Agent)
            .options(
                selectinload(Agent.areas),
                selectinload(Agent.roles),
                selectinload(Agent.fallback_agent),
            )
            .where(Agent.slug == slug)
        )
        return self.db.scalar(stmt)

    def get_agent_by_id(self, agent_id: str) -> Agent | None:
        stmt = (
            select(Agent)
            .options(
                selectinload(Agent.areas),
                selectinload(Agent.roles),
                selectinload(Agent.fallback_agent),
            )
            .where(Agent.id == agent_id)
        )
        return self.db.scalar(stmt)

    def get_agents_by_slugs(self, slugs: Sequence[str]) -> list[Agent]:
        if not slugs:
            return []
        stmt = (
            select(Agent)
            .options(
                selectinload(Agent.areas),
                selectinload(Agent.roles),
            )
            .where(Agent.slug.in_(slugs))
        )
        return list(self.db.scalars(stmt))

    def add_agent(self, agent: Agent) -> Agent:
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    # ---- Roles ----
    def list_roles(self) -> list[Role]:
        stmt = (
            select(Role)
            .options(
                selectinload(Role.agents),
                selectinload(Role.inherits_from),
            )
            .order_by(Role.level.desc(), Role.slug)
        )
        return list(self.db.scalars(stmt))

    def get_role_by_slug(self, slug: str) -> Role | None:
        stmt = (
            select(Role)
            .options(
                selectinload(Role.agents),
                selectinload(Role.inherits_from),
            )
            .where(Role.slug == slug)
        )
        return self.db.scalar(stmt)

    def get_role_by_id(self, role_id: str) -> Role | None:
        stmt = (
            select(Role)
            .options(
                selectinload(Role.agents),
                selectinload(Role.inherits_from),
            )
            .where(Role.id == role_id)
        )
        return self.db.scalar(stmt)

    def get_roles_by_slugs(self, slugs: Sequence[str]) -> list[Role]:
        if not slugs:
            return []
        stmt = (
            select(Role)
            .options(
                selectinload(Role.agents),
                selectinload(Role.inherits_from),
            )
            .where(Role.slug.in_(slugs))
        )
        return list(self.db.scalars(stmt))

    def add_role(self, role: Role) -> Role:
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)
        return role

    # ---- Junction helpers ----
    def replace_agent_areas(
        self,
        agent: Agent,
        areas: Sequence[Area],
        access_levels: dict[str, str] | None = None,
        default_access_level: str = "read",
    ) -> None:
        agent.area_links.clear()
        for area in areas:
            access_level = access_levels.get(area.slug) if access_levels else default_access_level
            agent.area_links.append(
                AgentArea(agent_id=agent.id, area_id=area.id, access_level=access_level)
            )
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)

    def replace_role_agents(self, role: Role, agents: Sequence[Agent]) -> None:
        role.role_agents.clear()
        for agent in agents:
            role.role_agents.append(RoleAgent(role_id=role.id, agent_id=agent.id))
        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)

    def replace_agent_roles(self, agent: Agent, roles: Sequence[Role]) -> None:
        agent.role_links.clear()
        for role in roles:
            agent.role_links.append(RoleAgent(role_id=role.id, agent_id=agent.id))
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)

    def replace_user_roles(self, user: User, roles: Sequence[Role]) -> None:
        stmt = select(UserRole).where(UserRole.user_id == user.id)
        existing = list(self.db.scalars(stmt))
        for rel in existing:
            self.db.delete(rel)
        self.db.flush()
        for role in roles:
            self.db.add(UserRole(user_id=user.id, role_id=role.id))
        self.db.commit()

    def get_user_by_id(self, user_id: str) -> User | None:
        return self.db.get(User, user_id)

    def list_superusers(self) -> list[User]:
        stmt = select(User).where(User.is_superuser.is_(True))
        return list(self.db.scalars(stmt))
