from types import SimpleNamespace

import pytest

import core_engine.module_loader as loader


def test_business_sim_module_exposes_required_interfaces() -> None:
    module = loader.load_module("business_sim")
    assert "agents" in module
    assert "tasks" in module
    assert "evaluation" in module
    assert "asset_transform" in module
    assert "progression" in module
    assert callable(getattr(module["progression"], "init_user", None))
    assert callable(getattr(module["progression"], "list_task_board", None))


def test_module_loader_rejects_missing_progression_interface(monkeypatch) -> None:
    def fake_import(target: str):
        if target.endswith(".agents"):
            return SimpleNamespace(AGENTS={})
        if target.endswith(".tasks"):
            return SimpleNamespace(get_task=lambda name: {})
        if target.endswith(".evaluation"):
            return SimpleNamespace(evaluate=lambda results: {})
        if target.endswith(".asset_transform"):
            return SimpleNamespace(to_asset=lambda results, evaluation: {})
        if target.endswith(".progression"):
            return SimpleNamespace()  # Missing required callables
        raise RuntimeError("unexpected import")

    monkeypatch.setattr(loader, "import_module", fake_import)

    with pytest.raises(loader.ModuleLoadError):
        loader.load_module("fake_module")
