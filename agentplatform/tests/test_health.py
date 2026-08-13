"""健康检查冒烟测试(TDD:先写测试,再实现)。

M0 验收:应用可起、/api/healthz 返回 200。
"""

from fastapi.testclient import TestClient

from agentplatform.main import app


def test_healthz_returns_ok() -> None:
    client = TestClient(app)
    resp = client.get("/api/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
