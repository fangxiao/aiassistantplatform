"""E2E 冒烟测试(对真实运行栈):健康/认证/会话 SSE/交互续跑/插件文件完整性。

只断言"系统集成缝"的行为,不重复单元测试覆盖的纯逻辑:
- 真实 HTTP + SSE 往返(messages / continue / diagnostics)
- 真实 LLM 网关参与(不 mock)——模型路由收口后仍应产出合法流
- 已注册插件实现文件在本机数据根内真实存在(T18.10 事故防线)
"""

import json
import os
import uuid

import httpx
import pytest

BASE_URL = os.environ.get("AGENTPLATFORM_E2E_BASE_URL", "http://localhost:8000")
pytestmark = pytest.mark.e2e


def _require_server() -> None:
    """服务未启动则整组跳过(冒烟测试只对真实栈有意义)。"""
    try:
        resp = httpx.get(f"{BASE_URL}/api/healthz", timeout=5)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"E2E 目标服务不可达 {BASE_URL}: {exc}")


def _parse_sse(raw: str) -> list[tuple[str, dict]]:
    """把 SSE 文本解析为 [(event, data)] 列表。"""
    events: list[tuple[str, dict]] = []
    lines = raw.split("\n")
    i = 0
    while i < len(lines) - 1:
        if lines[i].startswith("event: ") and lines[i + 1].startswith("data: "):
            try:
                data = json.loads(lines[i + 1][6:])
            except json.JSONDecodeError:
                data = {"raw": lines[i + 1][6:]}
            events.append((lines[i][7:], data))
            i += 2
        else:
            i += 1
    return events


@pytest.fixture(scope="module")
def auth_token() -> str:
    _require_server()
    email = f"e2e-smoke-{uuid.uuid4().hex[:8]}@test.dev"
    register = httpx.post(
        f"{BASE_URL}/api/auth/register",
        json={"email": email, "password": "E2eSmoke#2026", "nickname": "E2E冒烟"},
        timeout=15,
    )
    assert register.status_code == 201, register.text
    login = httpx.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": "E2eSmoke#2026"},
        timeout=15,
    )
    assert login.status_code == 200, login.text
    token = login.json().get("access_token") or login.json().get("token")
    assert token, f"登录未返回令牌: {login.text[:200]}"
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token: str) -> dict:
    return {"Authorization": f"Bearer {auth_token}"}


def _first_plugin_id(headers: dict) -> str | None:
    resp = httpx.get(f"{BASE_URL}/api/plugins", headers=headers, timeout=15)
    if resp.status_code != 200:
        return None
    items = resp.json()
    items = items if isinstance(items, list) else items.get("items", [])
    return items[0]["id"] if items else None


class TestSmoke:
    def test_healthz(self) -> None:
        _require_server()

    def test_chat_sse_roundtrip(self, auth_headers: dict) -> None:
        """真实 LLM 参与的会话往返:发消息应收到 delta/block_meta 与 done 事件。"""
        payload = {"plugin_id": _first_plugin_id(auth_headers)}
        created = httpx.post(
            f"{BASE_URL}/api/chat/sessions", headers=auth_headers, json=payload, timeout=30
        )
        assert created.status_code == 201, created.text
        sid = created.json()["id"]

        with httpx.stream(
            "POST",
            f"{BASE_URL}/api/chat/sessions/{sid}/messages",
            headers=auth_headers,
            json={"content": "你好"},
            timeout=180,
        ) as resp:
            assert resp.status_code == 200, resp.read()[:300]
            events = _parse_sse("".join(chunk for chunk in resp.iter_text()))

        kinds = [e for e, _ in events]
        assert "done" in kinds, f"缺少 done 事件,实际: {kinds}"
        assert any(e == "delta" and d.get("text", "").strip() for e, d in events), "没有任何正文流"

    def test_continue_endpoint_exists_and_streams(self, auth_headers: dict) -> None:
        """/continue 交互续跑端点必须真实存在(404 曾导致前端'[已中断]')。"""
        sessions = httpx.get(f"{BASE_URL}/api/chat/sessions", headers=auth_headers, timeout=15)
        assert sessions.status_code == 200
        sid = sessions.json()[0]["id"]
        with httpx.stream(
            "POST",
            f"{BASE_URL}/api/chat/sessions/{sid}/continue",
            headers=auth_headers,
            timeout=180,
        ) as resp:
            assert resp.status_code == 200, f"/continue 未生效: {resp.read()[:200]}"
            events = _parse_sse("".join(chunk for chunk in resp.iter_text()))
        assert any(e == "done" for e, _ in events)

    def test_deployed_plugin_impl_files_exist(self, auth_headers: dict) -> None:
        """插件文件完整性(T18.10):诊断接口应报告已注册实现文件无一缺失。

        直接对抗'容器重建丢文件,DB 路径仍在'的静默瘫痪。
        """
        resp = httpx.get(f"{BASE_URL}/api/diagnostics", timeout=30)
        assert resp.status_code == 200, resp.text
        checks = {c["name"]: c for c in resp.json()}
        assert "plugin_files" in checks, f"诊断缺少 plugin_files 项: {list(checks)}"
        assert checks["plugin_files"]["ok"], checks["plugin_files"]["detail"]
