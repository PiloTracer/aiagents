from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from .models import Agent, AgentArea, Area, Role, RoleAgent, UserRole
from .repository import CatalogRepository
from .service import _slugify
from app.core.database import Base


logger = logging.getLogger(__name__)


DEFAULT_AREAS = [
    {
        "slug": "area1",
        "name": "Demanda",
        "description": "Contiene toda la información oficial producida durante la demanda.",
        "access_level": "restricted",
    },
    {
        "slug": "area2",
        "name": "Jurisprudencia",
        "description": "Provee leyes, jurisprudencia y otros antecedentes legales relevantes.",
        "access_level": "restricted",
    },
    {
        "slug": "area3",
        "name": "Miscelaneos",
        "description": "Información adicional provista por las partes de manera no oficial.",
        "access_level": "restricted",
    },
    {
        "slug": "area4",
        "name": "General",
        "description": "Información de referencia y documentación transversal.",
        "access_level": "public",
    },
]


def _specialist_prompt(display_name: str, area_name: str, area_desc: str) -> str:
    guidelines = [
        f"You are {display_name}.",
        f"You specialise in the '{area_name}' knowledge area.",
        "Provide a comprehensive, deeply analytical answer grounded in the retrieved documents.",
        "Guidelines:",
        "1. Begin with a concise direct answer that cites the most relevant sources.",
        "2. Follow with detailed analysis that compares and explains the evidence from the context. Cite sources using [#].",
        "3. Quote or paraphrase key passages to justify each conclusion.",
        "4. List uncertainties, assumptions, or missing information that could change the answer.",
        "5. Suggest actionable next steps or follow-up questions when helpful.",
        "6. If the context includes Coverage Report or 'Hecho verificado' blocks about document completeness, treat them as authoritative:",
        "   - Do NOT claim that content is missing unless Coverage lists missing_pages.",
        "   - If continuity_ok is yes and missing_pages is none, explicitly state the document is complete and use it fully.",
        "Use only the supplied context. If it is insufficient, state that explicitly and describe what is missing.",
        "",
        "Primary focus:",
        area_desc,
    ]
    return "\n".join(guidelines)


DEFAULT_AGENTS = [
    {
        "slug": "agent0",
        "display_name": "Orchestrator",
        "description": "Coordina la conversación y selecciona el agente especialista adecuado.",
        "agent_type": "orchestrator",
        "capabilities": {"routing": True, "delegation": "single-agent"},
        "resource_permissions": {"allow": {"areas": ["*"], "mcps": ["google-drive-mcp", "fetch-mcp"]}},
        "system_prompt": "You are a router. Choose the single best agent slug for the user's question.",
        "temperature": 0.0,
        "max_tokens": 200,
        "execution_order": 0,
        "area_slugs": ["area1", "area2", "area3", "area4"],
        "access_levels": {"area1": "admin", "area2": "admin", "area3": "admin", "area4": "admin"},
        "role_slugs": [],
        "fallback_agent_slug": None,
    },
]


for idx, area_cfg in enumerate(DEFAULT_AREAS, start=1):
    DEFAULT_AGENTS.append(
        {
            "slug": f"agent{idx}",
            "display_name": f"Especialista {area_cfg['name']}",
            "description": f"Atiende consultas profundas relacionadas con el área '{area_cfg['name']}'.",
            "agent_type": "specialist",
            "capabilities": {
                "analysis_depth": "high",
                "primary_area": area_cfg["slug"],
            },
            "resource_permissions": {
                "allow": {
                    "areas": [area_cfg["slug"]],
                    "mcps": ["google-drive-mcp", "fetch-mcp"],
                }
            },
            "system_prompt": _specialist_prompt(
                f"Especialista {area_cfg['name']}",
                area_cfg["name"],
                area_cfg["description"],
            ),
            "temperature": 0.2,
            "max_tokens": 2048,
            "execution_order": idx * 10,
            "area_slugs": [area_cfg["slug"]],
            "access_levels": {area_cfg["slug"]: "read"},
            "role_slugs": [area_cfg["slug"]],
            "fallback_agent_slug": "agent0",
        }
    )


DEFAULT_ROLES = [
    {
        "slug": "administrator",
        "name": "Administrator",
        "description": "Full platform access, including catalog and security configuration.",
        "permissions": {
            "scope": "all",
            "areas": ["*"],
            "agents": ["*"],
            "can_manage_catalog": True,
            "can_manage_roles": True,
            "can_manage_users": True,
        },
        "level": 100,
        "is_system_role": True,
        "inherits_from": None,
        "agent_slugs": ["agent0", "agent1", "agent2", "agent3", "agent4"],
    },
    {
        "slug": "editor",
        "name": "Editor",
        "description": "Puede gestionar ingestiones y revisar la calidad de las respuestas.",
        "permissions": {
            "areas": ["area1", "area2", "area3", "area4"],
            "agents": ["agent1", "agent2", "agent3", "agent4"],
            "can_trigger_ingest": True,
        },
        "level": 70,
        "is_system_role": False,
        "inherits_from": "contributor",
        "agent_slugs": ["agent1", "agent2", "agent3", "agent4"],
    },
    {
        "slug": "contributor",
        "name": "Contributor",
        "description": "Puede consultar la base de conocimiento y proponer nuevas fuentes.",
        "permissions": {
            "areas": ["area4"],
            "agents": ["agent4"],
        },
        "level": 50,
        "is_system_role": False,
        "inherits_from": None,
        "agent_slugs": ["agent4"],
    },
    {
        "slug": "agent1",
        "name": "Agent1",
        "description": "Acceso dedicado al especialista del área Demanda.",
        "permissions": {"areas": ["area1"], "agents": ["agent1"]},
        "level": 20,
        "is_system_role": False,
        "inherits_from": None,
        "agent_slugs": ["agent1"],
    },
    {
        "slug": "agent2",
        "name": "Agent2",
        "description": "Acceso dedicado al especialista del área Jurisprudencia.",
        "permissions": {"areas": ["area2"], "agents": ["agent2"]},
        "level": 20,
        "is_system_role": False,
        "inherits_from": None,
        "agent_slugs": ["agent2"],
    },
    {
        "slug": "agent3",
        "name": "Agent3",
        "description": "Acceso dedicado al especialista del área Miscelaneos.",
        "permissions": {"areas": ["area3"], "agents": ["agent3"]},
        "level": 20,
        "is_system_role": False,
        "inherits_from": None,
        "agent_slugs": ["agent3"],
    },
    {
        "slug": "agent4",
        "name": "Agent4",
        "description": "Acceso dedicado al especialista del área General.",
        "permissions": {"areas": ["area4"], "agents": ["agent4"]},
        "level": 20,
        "is_system_role": False,
        "inherits_from": None,
        "agent_slugs": ["agent4"],
    },
]


def ensure_default_catalog(db: Session) -> None:
    """
    Seed catalog tables with default areas, agents, roles, and relationships.
    Safe to run multiple times; creates missing records without overwriting
    existing customisations.
    """
    try:
        bind = db.get_bind()
    except Exception:  # pragma: no cover - defensive guard
        bind = None

    if bind is not None:
        try:
            inspector = inspect(bind)
            tables = [
                Area.__table__,
                Agent.__table__,
                Role.__table__,
                AgentArea.__table__,
                RoleAgent.__table__,
                UserRole.__table__,
            ]
            missing: list[str] = []
            for table in tables:
                if not inspector.has_table(table.name):
                    table.create(bind, checkfirst=True)
                    missing.append(table.name)
            if missing:
                logger.info("Created catalog tables: %s", ", ".join(missing))
        except Exception as exc:
            logger.warning("Catalog metadata creation failed: %s", exc)

    try:
        db.execute(text("SELECT 1 FROM areas LIMIT 1"))
    except Exception as exc:
        db.rollback()
        logger.debug("Catalog tables not ready yet: %s", exc)
        return

    repo = CatalogRepository(db)
    areas_by_slug: dict[str, Area] = {}

    # -- Ensure areas --
    for cfg in DEFAULT_AREAS:
        slug = _slugify(cfg["slug"])
        area = repo.get_area_by_slug(slug)
        if not area:
            area = Area(
                slug=slug,
                name=cfg["name"],
                description=cfg["description"],
                access_level=cfg["access_level"],
                vector_collection=f"rag_{slug}",
                is_active=True,
            )
            db.add(area)
            db.flush()
            logger.info("Seeded area '%s'", slug)
        areas_by_slug[slug] = area

    db.commit()

    # -- Ensure agents --
    agents_by_slug: dict[str, Agent] = {}
    for cfg in DEFAULT_AGENTS:
        slug = _slugify(cfg["slug"])
        agent = repo.get_agent_by_slug(slug)
        if not agent:
            fallback_id = None
            fallback_slug = cfg.get("fallback_agent_slug")
            if fallback_slug:
                fallback_slug = _slugify(fallback_slug)
                fallback_agent = agents_by_slug.get(fallback_slug) or repo.get_agent_by_slug(fallback_slug)
                if fallback_agent:
                    fallback_id = fallback_agent.id
            agent = Agent(
                slug=slug,
                display_name=cfg["display_name"],
                description=cfg["description"],
                agent_type=cfg["agent_type"],
                capabilities=cfg.get("capabilities") or {},
                resource_permissions=cfg.get("resource_permissions") or {},
                system_prompt=cfg["system_prompt"],
                temperature=cfg.get("temperature", 0.2),
                max_tokens=cfg.get("max_tokens", 2048),
                is_active=True,
                execution_order=cfg.get("execution_order", 0),
                fallback_agent_id=fallback_id,
            )
            db.add(agent)
            db.flush()
            logger.info("Seeded agent '%s'", slug)
        agents_by_slug[slug] = agent

    db.commit()

    # -- Ensure agent area relationships --
    for cfg in DEFAULT_AGENTS:
        slug = _slugify(cfg["slug"])
        agent = agents_by_slug.get(slug) or repo.get_agent_by_slug(slug)
        if not agent:
            continue
        area_slugs = cfg.get("area_slugs", [])
        access_levels = cfg.get("access_levels", {})
        for area_slug in area_slugs:
            area_slug_norm = _slugify(area_slug)
            area = areas_by_slug.get(area_slug_norm) or repo.get_area_by_slug(area_slug_norm)
            if not area:
                continue
            exists_stmt = select(AgentArea).where(
                AgentArea.agent_id == agent.id,
                AgentArea.area_id == area.id,
            )
            link = db.scalar(exists_stmt)
            if not link:
                db.add(
                    AgentArea(
                        agent_id=agent.id,
                        area_id=area.id,
                        access_level=access_levels.get(area_slug, access_levels.get(area_slug_norm, "read")),
                    )
                )
                logger.info("Linked agent '%s' with area '%s'", slug, area_slug_norm)
    db.commit()

    # -- Ensure roles --
    roles_by_slug: dict[str, Role] = {}
    for cfg in DEFAULT_ROLES:
        slug = _slugify(cfg["slug"])
        role = repo.get_role_by_slug(slug)
        if not role:
            inherits_from_id = None
            parent_slug = cfg.get("inherits_from")
            if parent_slug:
                parent_slug_norm = _slugify(parent_slug)
                parent = roles_by_slug.get(parent_slug_norm) or repo.get_role_by_slug(parent_slug_norm)
                if parent:
                    inherits_from_id = parent.id
            role = Role(
                slug=slug,
                name=cfg["name"],
                description=cfg.get("description"),
                permissions=cfg.get("permissions") or {},
                level=cfg.get("level", 0),
                is_system_role=cfg.get("is_system_role", False),
                inherits_from_id=inherits_from_id,
            )
            db.add(role)
            db.flush()
            logger.info("Seeded role '%s'", slug)
        roles_by_slug[slug] = role

    db.commit()

    # -- Ensure role inheritance links (second pass) --
    inheritance_updated = False
    for cfg in DEFAULT_ROLES:
        slug = _slugify(cfg["slug"])
        parent_slug = cfg.get("inherits_from")
        if not parent_slug:
            continue
        role = roles_by_slug.get(slug) or repo.get_role_by_slug(slug)
        parent_slug_norm = _slugify(parent_slug)
        parent = roles_by_slug.get(parent_slug_norm) or repo.get_role_by_slug(parent_slug_norm)
        if role and parent and role.inherits_from_id != parent.id:
            role.inherits_from_id = parent.id
            db.add(role)
            inheritance_updated = True
    if inheritance_updated:
        db.commit()

    # -- Ensure role-agent relationships --
    for cfg in DEFAULT_ROLES:
        role_slug = _slugify(cfg["slug"])
        role = roles_by_slug.get(role_slug) or repo.get_role_by_slug(role_slug)
        if not role:
            continue
        for agent_slug in cfg.get("agent_slugs", []):
            agent_slug_norm = _slugify(agent_slug)
            agent = agents_by_slug.get(agent_slug_norm) or repo.get_agent_by_slug(agent_slug_norm)
            if not agent:
                continue
            exists_stmt = select(RoleAgent).where(
                RoleAgent.role_id == role.id,
                RoleAgent.agent_id == agent.id,
            )
            link = db.scalar(exists_stmt)
            if not link:
                db.add(RoleAgent(role_id=role.id, agent_id=agent.id))
                logger.info("Linked role '%s' with agent '%s'", role_slug, agent_slug_norm)
    db.commit()

    # -- Ensure admin users hold administrator role --
    admin_role = roles_by_slug.get("administrator") or repo.get_role_by_slug("administrator")
    if admin_role:
        superusers = repo.list_superusers()
        for user in superusers:
            stmt = select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.role_id == admin_role.id,
            )
            mapping = db.scalar(stmt)
            if not mapping:
                db.add(UserRole(user_id=user.id, role_id=admin_role.id))
                logger.info("Granted administrator role to user %s", user.email)
        db.commit()
