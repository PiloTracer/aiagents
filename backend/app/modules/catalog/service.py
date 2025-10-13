from __future__ import annotations

import re
from typing import Sequence

from sqlalchemy.orm import Session

from .models import Agent, Area, Role
from .repository import CatalogRepository
from .schemas import (
    AgentCreate,
    AgentRead,
    AgentUpdate,
    AreaCreate,
    AreaRead,
    AreaUpdate,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    UserRoleAssignmentRequest,
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or value.strip().lower()


class CatalogService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = CatalogRepository(db)

    # ---- Areas ----
    def list_areas(self) -> list[AreaRead]:
        areas = self.repo.list_areas()
        return [self._to_area_read(area) for area in areas]

    def create_area(self, data: AreaCreate) -> AreaRead:
        slug = _slugify(data.slug)
        if self.repo.get_area_by_slug(slug):
            raise ValueError(f"Area slug '{slug}' already exists")
        vector_collection = data.vector_collection or f"rag_{slug}"
        area = Area(
            slug=slug,
            name=data.name.strip(),
            description=data.description,
            vector_collection=vector_collection,
            access_level=data.access_level,
            is_active=data.is_active,
        )
        persisted = self.repo.add_area(area)
        return self._to_area_read(persisted)

    def update_area(self, area_id: str, data: AreaUpdate) -> AreaRead:
        area = self.repo.get_area_by_id(area_id)
        if not area:
            raise ValueError("Area not found")
        if data.name is not None:
            area.name = data.name.strip()
        if data.description is not None:
            area.description = data.description
        if data.vector_collection is not None:
            area.vector_collection = data.vector_collection
        if data.access_level is not None:
            area.access_level = data.access_level
        if data.is_active is not None:
            area.is_active = data.is_active
        self.db.add(area)
        self.db.commit()
        self.db.refresh(area)
        return self._to_area_read(area)

    # ---- Agents ----
    def list_agents(self) -> list[AgentRead]:
        agents = self.repo.list_agents()
        return [self._to_agent_read(agent) for agent in agents]

    def create_agent(self, data: AgentCreate) -> AgentRead:
        slug = _slugify(data.slug)
        if self.repo.get_agent_by_slug(slug):
            raise ValueError(f"Agent slug '{slug}' already exists")
        fallback_agent_id = None
        if data.fallback_agent_slug:
            fallback = self.repo.get_agent_by_slug(_slugify(data.fallback_agent_slug))
            if not fallback:
                raise ValueError(f"Fallback agent '{data.fallback_agent_slug}' not found")
            fallback_agent_id = fallback.id

        agent = Agent(
            slug=slug,
            display_name=data.display_name.strip(),
            description=data.description,
            agent_type=data.agent_type,
            capabilities=data.capabilities or {},
            resource_permissions=data.resource_permissions or {},
            system_prompt=data.system_prompt,
            temperature=data.temperature,
            max_tokens=data.max_tokens,
            is_active=data.is_active,
            execution_order=data.execution_order,
            fallback_agent_id=fallback_agent_id,
        )
        persisted = self.repo.add_agent(agent)

        if data.area_slugs:
            area_slugs = [_slugify(slug) for slug in data.area_slugs]
            areas = self._ensure_areas(area_slugs)
            self.repo.replace_agent_areas(persisted, areas)
            persisted = self.repo.get_agent_by_id(persisted.id) or persisted

        if data.role_slugs:
            roles = self._ensure_roles([_slugify(slug) for slug in data.role_slugs])
            self.repo.replace_agent_roles(persisted, roles)
            persisted = self.repo.get_agent_by_id(persisted.id) or persisted

        return self._to_agent_read(persisted)

    def update_agent(self, agent_id: str, data: AgentUpdate) -> AgentRead:
        agent = self.repo.get_agent_by_id(agent_id)
        if not agent:
            raise ValueError("Agent not found")

        if data.display_name is not None:
            agent.display_name = data.display_name.strip()
        if data.description is not None:
            agent.description = data.description
        if data.agent_type is not None:
            agent.agent_type = data.agent_type
        if data.capabilities is not None:
            agent.capabilities = data.capabilities
        if data.resource_permissions is not None:
            agent.resource_permissions = data.resource_permissions
        if data.system_prompt is not None:
            agent.system_prompt = data.system_prompt
        if data.temperature is not None:
            agent.temperature = data.temperature
        if data.max_tokens is not None:
            agent.max_tokens = data.max_tokens
        if data.is_active is not None:
            agent.is_active = data.is_active
        if data.execution_order is not None:
            agent.execution_order = data.execution_order
        if data.fallback_agent_slug is not None:
            if data.fallback_agent_slug:
                fallback = self.repo.get_agent_by_slug(_slugify(data.fallback_agent_slug))
                if not fallback:
                    raise ValueError(f"Fallback agent '{data.fallback_agent_slug}' not found")
                if fallback.id == agent.id:
                    raise ValueError("Agent cannot fallback to itself")
                agent.fallback_agent_id = fallback.id
            else:
                agent.fallback_agent_id = None

        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)

        if data.area_slugs is not None:
            area_slugs = [_slugify(slug) for slug in data.area_slugs]
            areas = self._ensure_areas(area_slugs)
            access_levels = {area.slug: "read" for area in areas}
            self.repo.replace_agent_areas(agent, areas, access_levels=access_levels)
            agent = self.repo.get_agent_by_id(agent.id) or agent

        if data.role_slugs is not None:
            roles = self._ensure_roles([_slugify(slug) for slug in data.role_slugs])
            self.repo.replace_agent_roles(agent, roles)
            agent = self.repo.get_agent_by_id(agent.id) or agent

        return self._to_agent_read(agent)

    # ---- Roles ----
    def list_roles(self) -> list[RoleRead]:
        roles = self.repo.list_roles()
        return [self._to_role_read(role) for role in roles]

    def create_role(self, data: RoleCreate) -> RoleRead:
        slug = _slugify(data.slug or data.name)
        if self.repo.get_role_by_slug(slug):
            raise ValueError(f"Role slug '{slug}' already exists")

        inherits_from_id = None
        if data.inherits_from_slug:
            parent = self.repo.get_role_by_slug(_slugify(data.inherits_from_slug))
            if not parent:
                raise ValueError(f"Parent role '{data.inherits_from_slug}' not found")
            inherits_from_id = parent.id

        role = Role(
            slug=slug,
            name=data.name.strip(),
            description=data.description,
            permissions=data.permissions or {},
            level=data.level,
            is_system_role=data.is_system_role,
            inherits_from_id=inherits_from_id,
        )
        persisted = self.repo.add_role(role)

        if data.agent_slugs:
            agents = self._ensure_agents([_slugify(slug) for slug in data.agent_slugs])
            self.repo.replace_role_agents(persisted, agents)
            persisted = self.repo.get_role_by_id(persisted.id) or persisted

        return self._to_role_read(persisted)

    def update_role(self, role_id: str, data: RoleUpdate) -> RoleRead:
        role = self.repo.get_role_by_id(role_id)
        if not role:
            raise ValueError("Role not found")

        if data.name is not None:
            role.name = data.name.strip()
        if data.description is not None:
            role.description = data.description
        if data.permissions is not None:
            role.permissions = data.permissions
        if data.level is not None:
            role.level = data.level
        if data.is_system_role is not None:
            role.is_system_role = data.is_system_role
        if data.inherits_from_slug is not None:
            if data.inherits_from_slug:
                parent = self.repo.get_role_by_slug(_slugify(data.inherits_from_slug))
                if not parent:
                    raise ValueError(f"Parent role '{data.inherits_from_slug}' not found")
                if parent.id == role.id:
                    raise ValueError("Role cannot inherit from itself")
                role.inherits_from_id = parent.id
            else:
                role.inherits_from_id = None

        self.db.add(role)
        self.db.commit()
        self.db.refresh(role)

        if data.agent_slugs is not None:
            agents = self._ensure_agents([_slugify(slug) for slug in data.agent_slugs])
            self.repo.replace_role_agents(role, agents)
            role = self.repo.get_role_by_id(role.id) or role

        return self._to_role_read(role)

    # ---- User Roles ----
    def assign_roles_to_user(self, user_id: str, data: UserRoleAssignmentRequest) -> None:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        roles = self._ensure_roles([_slugify(slug) for slug in data.role_slugs])
        self.repo.replace_user_roles(user, roles)

    # ---- Helper converters ----
    def _ensure_areas(self, slugs: Sequence[str]) -> list[Area]:
        areas = self.repo.get_areas_by_slugs(slugs)
        missing = sorted(set(slugs) - {area.slug for area in areas})
        if missing:
            raise ValueError(f"Areas not found: {', '.join(missing)}")
        return areas

    def _ensure_agents(self, slugs: Sequence[str]) -> list[Agent]:
        agents = self.repo.get_agents_by_slugs(slugs)
        missing = sorted(set(slugs) - {agent.slug for agent in agents})
        if missing:
            raise ValueError(f"Agents not found: {', '.join(missing)}")
        return agents

    def _ensure_roles(self, slugs: Sequence[str]) -> list[Role]:
        roles = self.repo.get_roles_by_slugs(slugs)
        missing = sorted(set(slugs) - {role.slug for role in roles})
        if missing:
            raise ValueError(f"Roles not found: {', '.join(missing)}")
        return roles

    def _to_area_read(self, area: Area) -> AreaRead:
        return AreaRead.model_validate(
            {
                "id": area.id,
                "slug": area.slug,
                "name": area.name,
                "description": area.description,
                "vector_collection": area.vector_collection,
                "access_level": area.access_level,
                "is_active": area.is_active,
                "created_at": area.created_at,
                "updated_at": area.updated_at,
                "agent_slugs": [agent.slug for agent in getattr(area, "agents", [])],
            }
        )

    def _to_agent_read(self, agent: Agent) -> AgentRead:
        fallback_slug = agent.fallback_agent.slug if agent.fallback_agent else None
        return AgentRead.model_validate(
            {
                "id": agent.id,
                "slug": agent.slug,
                "display_name": agent.display_name,
                "description": agent.description,
                "agent_type": agent.agent_type,
                "capabilities": agent.capabilities,
                "resource_permissions": agent.resource_permissions,
                "system_prompt": agent.system_prompt,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
                "is_active": agent.is_active,
                "execution_order": agent.execution_order,
                "fallback_agent_id": agent.fallback_agent_id,
                "fallback_agent_slug": fallback_slug,
                "created_at": agent.created_at,
                "updated_at": agent.updated_at,
                "area_slugs": [area.slug for area in getattr(agent, "areas", [])],
                "role_slugs": [role.slug for role in getattr(agent, "roles", [])],
            }
        )

    def _to_role_read(self, role: Role) -> RoleRead:
        inherits_from_slug = role.inherits_from.slug if role.inherits_from else None
        return RoleRead.model_validate(
            {
                "id": role.id,
                "slug": role.slug,
                "name": role.name,
                "description": role.description,
                "permissions": role.permissions,
                "level": role.level,
                "is_system_role": role.is_system_role,
                "inherits_from_id": role.inherits_from_id,
                "inherits_from_slug": inherits_from_slug,
                "created_at": role.created_at,
                "updated_at": role.updated_at,
                "agent_slugs": [agent.slug for agent in getattr(role, "agents", [])],
            }
        )

