from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_api_layer_has_no_direct_business_sim_imports() -> None:
    run_task_src = _read("api/run_task.py")
    users_src = _read("api/routes/users.py")

    forbidden = "game_modules.business_sim"
    assert forbidden not in run_task_src
    assert forbidden not in users_src


def test_api_layer_uses_module_facade() -> None:
    run_task_src = _read("api/run_task.py")
    users_src = _read("api/routes/users.py")

    assert "ModuleFacade" in run_task_src
    assert "ModuleFacade" in users_src
