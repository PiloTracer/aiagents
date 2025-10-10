from __future__ import annotations

import importlib
import pkgutil
from typing import Iterable, List

from fastapi import APIRouter


MODULES_PACKAGE = "app.modules"


def iter_submodules(package: str) -> Iterable[str]:
    pkg = importlib.import_module(package)
    for m in pkgutil.iter_modules(pkg.__path__):
        if m.ispkg:
            yield f"{package}.{m.name}"


def import_module_models(module_pkg: str) -> None:
    try:
        importlib.import_module(f"{module_pkg}.models")
    except ModuleNotFoundError:
        # Module might be pure Python or not define DB models
        pass


def collect_routers() -> List[APIRouter]:
    routers: List[APIRouter] = []
    for mod in iter_submodules(MODULES_PACKAGE):
        # Ensure models are registered before schema initialization
        import_module_models(mod)
        try:
            router_mod = importlib.import_module(f"{mod}.router")
        except ModuleNotFoundError:
            continue
        router = getattr(router_mod, "router", None)
        if router is not None:
            routers.append(router)
    return routers
