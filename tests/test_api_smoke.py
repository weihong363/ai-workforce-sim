from fastapi.testclient import TestClient

from api.app import app


def test_health_endpoint() -> None:
    """Test that health endpoint returns expected configuration."""
    client = TestClient(app)
    
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"
    assert health_resp.json()["active_game_module"] == "business_sim"
    assert isinstance(health_resp.json()["use_mock_provider"], bool)
