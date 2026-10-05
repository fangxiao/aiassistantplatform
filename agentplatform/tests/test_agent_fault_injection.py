"""系统化错误注入矩阵(Harness 尾项/需求 011 A4 补全/ADR 0010)。

设计 016 §6 的注入矩阵落地:
- 矩阵 1:classify_exception 六分类 × 代表异常(纯函数,参数化)
- 矩阵 2:SSE error 事件分类透出(loop 层注入 transient/tool_failure 两类锚点;
  断流/session 失效回归在 test_chat_api,部署态自愈在 test_plugin_loader 等)
"""

import asyncio

import pytest

from agentplatform.core.agent.errors import (
    AgentExecError,
    AgentLoopError,
    ErrorKind,
    classify_exception,
)

# ── 矩阵 1:classify_exception 分类(六类 × 代表异常)────────

MATRIX = [
    # (异常, 期望类别, 期望可续跑)
    (asyncio.TimeoutError(), ErrorKind.transient, True),
    (ConnectionError("connection reset"), ErrorKind.transient, True),
    (AgentLoopError("LLM 调用失败"), ErrorKind.transient, True),
    (TimeoutError("read timed out"), ErrorKind.transient, True),
    (AgentExecError("实现文件不存在: tool_x"), ErrorKind.deploy_broken, False),
    (AgentExecError("impl 文件缺失"), ErrorKind.deploy_broken, False),
    (AgentExecError("无法加载插件模块 foo"), ErrorKind.deploy_broken, False),
    (AgentExecError("缺少 impl_path"), ErrorKind.deploy_broken, False),
    (AgentExecError("参数校验失败: query 必填"), ErrorKind.tool_failure, False),
    (RuntimeError("连接池耗尽 connection closed"), ErrorKind.transient, True),
    (ValueError("意外的内部状态"), ErrorKind.internal, True),
    (KeyError("round"), ErrorKind.internal, True),
]


@pytest.mark.parametrize(("exc", "kind", "resumable"), MATRIX)
def test_classify_matrix(exc, kind, resumable):
    got_kind, got_resumable = classify_exception(exc)
    assert got_kind is kind, f"{exc!r} 应分类为 {kind},实际 {got_kind}"
    assert got_resumable is resumable


def test_deploy_broken_markers_are_the_contract():
    """部署态断线特征串与 ADR 0010 声明一致(防漂移)。"""
    from agentplatform.core.agent.errors import _DEPLOY_BROKEN_MARKERS

    assert set(_DEPLOY_BROKEN_MARKERS) == {
        "实现文件不存在", "impl 文件缺失", "无法加载插件模块", "缺少 impl_path",
    }


# ── 矩阵 2:SSE error 事件分类透出 ─────────────────────────────


async def _sse_error_of(client, session, monkeypatch, exc: BaseException) -> dict:
    """向会话发消息(注入 stream_agent 抛异常),解析 error 事件的 JSON 数据。"""
    import json

    from agentplatform.core.chat import service as chat_service

    async def _fake_stream(*a, **k):
        raise exc
        yield  # pragma: no cover

    monkeypatch.setattr(chat_service, "stream_agent", _fake_stream)

    from agentplatform.core.session.model import Session

    sess = Session(user_id="u-inject", title="注入")
    session.add(sess)
    await session.commit()

    resp = await client.post(f"/api/chat/sessions/{sess.id}/messages", json={"content": "hi"})
    assert resp.status_code == 200
    data = ""
    for line in resp.text.splitlines():
        if line.startswith("data: ") and '"kind"' in line:
            data = line[len("data: "):]
            break
    assert data, f"未捕获 error 事件,响应: {resp.text[:300]}"
    return json.loads(data)


async def test_sse_transient_error_event(client, session, monkeypatch):
    """AgentLoopError → error 事件 kind=transient(六类锚点之一)。"""
    evt = await _sse_error_of(client, session, monkeypatch, AgentLoopError("上游 503"))
    assert evt["code"] in ("chat_error", "agent_error")
    assert evt["kind"] == "transient"
    assert "上游 503" in evt["message"]


async def test_sse_tool_failure_error_event(client, session, monkeypatch):
    """AgentExecError(非部署态)→ error 事件 kind=tool_failure(六类锚点之二)。"""
    evt = await _sse_error_of(
        client, session, monkeypatch, AgentExecError("参数校验失败: query 必填")
    )
    assert evt["kind"] == "tool_failure"


async def test_sse_internal_error_event(client, session, monkeypatch):
    """未知异常 → kind=internal 且 resumable 兜底为真(六类锚点之三)。"""
    evt = await _sse_error_of(client, session, monkeypatch, ValueError("内部状态崩了"))
    assert evt["kind"] == "internal"
