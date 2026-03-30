"""Facade over game modules to keep API layer module-agnostic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from core_engine.config import get_settings
from core_engine.module_loader import load_module, resolve_module_name


@dataclass
class ModuleFacade:
    module_name: str
    components: Dict[str, object]

    @classmethod
    def from_name(cls, module_name: Optional[str] = None) -> "ModuleFacade":
        settings = get_settings()
        selected = resolve_module_name(module_name, settings.active_game_module)
        return cls(module_name=selected, components=load_module(selected))

    @property
    def agents(self) -> object:
        return self.components["agents"]

    @property
    def tasks(self) -> object:
        return self.components["tasks"]

    @property
    def evaluation(self) -> object:
        return self.components["evaluation"]

    @property
    def asset_transform(self) -> object:
        return self.components["asset_transform"]

    @property
    def progression(self) -> object:
        return self.components["progression"]

    def get_task(self, task_id: str) -> dict:
        return self.tasks.get_task(task_id)

    def list_tasks(self) -> Dict[str, Dict[str, object]]:
        if callable(getattr(self.tasks, "list_tasks", None)):
            return self.tasks.list_tasks()
        return {}
