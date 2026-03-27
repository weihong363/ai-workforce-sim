from core_engine.agent_controller import AgentController
from core_engine.config import get_settings


class DummyClient:
    def complete(self, prompt: str) -> str:
        return "ok"


def test_junior_delay_range_larger_than_senior(monkeypatch) -> None:
    settings = get_settings()
    controller = AgentController(settings=settings, llm_client=DummyClient(), enable_agent_cache=False)

    captured = {"ranges": [], "sleeps": []}

    def fake_uniform(a: float, b: float) -> float:
        captured["ranges"].append((a, b))
        return (a + b) / 2

    def fake_sleep(x: float) -> None:
        captured["sleeps"].append(x)

    monkeypatch.setattr("core_engine.agent_controller.random.uniform", fake_uniform)
    monkeypatch.setattr("core_engine.agent_controller.time.sleep", fake_sleep)

    controller.run_agent(
        agent_name="a",
        task_input="t",
        agent_profile={"level": "junior", "obedience": 0.8, "initiative": 0.2, "effort": 0.6, "affinity": 0.5},
    )
    controller.run_agent(
        agent_name="b",
        task_input="t",
        agent_profile={"level": "senior", "obedience": 0.4, "initiative": 0.7, "effort": 0.7, "affinity": 0.5},
    )

    junior_range = captured["ranges"][0]
    senior_range = captured["ranges"][1]

    assert junior_range[0] > senior_range[0]
    assert junior_range[1] > senior_range[1]
    assert captured["sleeps"][0] > captured["sleeps"][1]
