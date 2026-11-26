"""
Extensible Integrations and Connector Engine for Nova AI.
Inspired by PocketPaw's dynamic plugin and tools ecosystem.
Zero third-party pip dependencies - Python standard library only.
"""
import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("integrations")


class BaseIntegration:
    name: str = "base"
    description: str = ""

    def run(self, cfg: Dict[str, Any], raw_arg: str) -> str:
        raise NotImplementedError("Integrations must implement the run() method.")


REGISTRY: Dict[str, BaseIntegration] = {}


def load_integrations() -> Dict[str, BaseIntegration]:
    """
    Scans the integrations/ directory and dynamically registers all BaseIntegration subclasses.
    """
    global REGISTRY
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        pkg_dir = Path(sys._MEIPASS) / "integrations"
    else:
        pkg_dir = Path(__file__).resolve().parent

    for item in pkg_dir.glob("*.py"):
        if item.stem in ("__init__", "base"):
            continue
        mod_name = f"integrations.{item.stem}"
        try:
            mod = importlib.import_module(mod_name)
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseIntegration)
                    and attr is not BaseIntegration
                ):
                    inst = attr()
                    REGISTRY[inst.name.lower()] = inst
        except Exception as e:
            logger.warning(f"[Integrations] Failed to load integration '{item.name}': {e}")

    return REGISTRY


def get_integration(name: str) -> Optional[BaseIntegration]:
    """Retrieve loaded integration instance by name."""
    if not REGISTRY:
        load_integrations()
    return REGISTRY.get(name.lower())
