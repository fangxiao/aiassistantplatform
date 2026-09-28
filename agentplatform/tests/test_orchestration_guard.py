"""T18.3 编排保障测试:required_tools 缺失→系统校验注入补调(有界一次)。"""

import json

import pytest

from agentplatform.core.agent.loop import run_agent
from agentplatform.core.registry.model import SkillTool, SkillToolKind, SkillToolSource


def _skill(rid: str, schema_extra: dict | None = None) -> SkillTool:
    schema = {"parameters": {"type": "object"}}
    schema.update(schema_extra or {})
    return SkillTool(
        id=rid, kind=SkillToolKind.skill, name=rid.split(":", 1)[1],
        version="1.0.0", source=SkillToolSource.private, schema_=schema,
        impl_path="", description="",
    )


def _tool(tid: str) -> SkillTool:
    return SkillTool(
        id=tid, kind=SkillToolKind.tool, name=tid.split(":", 1)[1],
        version="1.0.0", source=SkillToolSource.private, schema_={},
        impl_path="", description="",
    )


async def _register_rows(session, skill: SkillTool, tool: SkillTool | None = None) -> None:
    """把 skill/tool 登记进 DB(loop 经 resolve 取行,schema_ 携带 required_tools)。"""
    from agentplatform.core.registry.service import register

    await register(
        session, resource_id=skill.id, kind=skill.kind, name=skill.name,
        version=skill.version, source=SkillToolSource.private,
        schema_=skill.schema_, impl_path="", owner_id="og-test",
    )
    if tool is not None:
        await register(
            session, resource_id=tool.id, kind=tool.kind, name=tool.name,
            version=tool.version, source=SkillToolSource.private,
            schema_=tool.schema_ or {"parameters": {"type": "object"}},
            impl_path="", owner_id="og-test",
        )
    await session.commit()


class _ScriptedClient:
    """按脚本逐轮响应:round1 调 skill 但不调必经 tool;round2(校验后)补调。"""

    def __init__(self, rounds: list[str]):
        self.rounds = list(rounds)
        self.seen_prompts: list[list[dict]] = []

    async def stream(self, messages, tools=None):
        """async generator 形态(与真实 client 一致)。"""
        self.seen_prompts.append([dict(m) for m in messages])  # 存副本(loop 会原地 append)
        text = self.rounds.pop(0)
        if text.startswith("CALL:"):
            from agentplatform.core.llm.client import ToolCall

            yield _Ev(tool_call=ToolCall(id="c1", name=text[5:], arguments="{}"))
        else:
            for ch in (text[i:i + 8] for i in range(0, len(text), 8)):
                yield _Ev(delta=ch)


class _Ev:
    def __init__(self, delta: str | None = None, tool_call=None):
        self.type = "tool_call" if tool_call else "delta"
        self.text = delta
        self.tool_call = tool_call


@pytest.mark.asyncio
class TestOrchestrationGuard:
    async def test_missing_required_tool_triggers_nudge_and_completion(self, session, monkeypatch) -> None:
        """skill 声明 required_tools 但模型跳过 → 注入系统校验 → 补调后交付。"""
        skill = _skill("skill:w", {"required_tools": ["tool:must"]})
        tool = _tool("tool:must")
        await _register_rows(session, skill, tool)

        from agentplatform.core.agent import loop as loop_mod

        # execute_skill:返回提示词文本
        async def _fake_skill(res, args, skill_call=None):
            return "技能执行完成"

        monkeypatch.setattr(loop_mod, "execute_skill", _fake_skill)
        # execute_tool:必经工具返回成功
        async def _fake_tool(res, args):
            return json.dumps({"ok": True})

        monkeypatch.setattr(loop_mod, "execute_tool", _fake_tool)

        client = _ScriptedClient([
            "CALL:skill__w",          # 第 1 轮:只调 skill
            "交付完成(但漏了必经工具)",  # 第 2 轮:无调用 → 触发系统校验注入
            "CALL:tool__must",        # 第 3 轮:按校验提示补调
            "最终交付:已含必经步骤",
        ])
        result = await run_agent(session, client, resource_ids=[skill.id, tool.id],
                                 user_message="做交付")
        assert "最终交付" in result.text
        assert any(tc.id == "tool:must" for tc in result.tool_traces)
        # 系统校验注入确实发生(第 2 轮 prompt 含校验语)
        assert any("系统校验" in json.dumps([m.get("content") or "" for m in msgs], ensure_ascii=False)
                   for msgs in client.seen_prompts[1:])

    async def test_nudge_bounded_once(self, session, monkeypatch) -> None:
        """补调后仍不调用:不再二次注入,按模型如实输出收尾(有界)。"""
        skill = _skill("skill:w", {"required_tools": ["tool:must"]})
        tool = _tool("tool:must")
        await _register_rows(session, skill, tool)
        from agentplatform.core.agent import loop as loop_mod

        async def _fake_skill(res, args, skill_call=None):
            return "技能执行完成"

        monkeypatch.setattr(loop_mod, "execute_skill", _fake_skill)
        client = _ScriptedClient([
            "CALL:skill__w",
            "无法调用该工具,如实说明",   # 触发校验注入(第 1 次)
            "最终如实交付说明",          # 仍不调用 → 不再注入,按模型输出收尾
        ])
        result = await run_agent(session, client, resource_ids=[skill.id, tool.id],
                                 user_message="做交付")
        assert "如实" in result.text
        # 注入计数:仅统计"以校验消息结尾"的轮次(注入会留存于后续 prompt,不能按出现次数计)
        nudge_count = sum(
            1 for msgs in client.seen_prompts
            if msgs and "系统校验" in ((msgs[-1].get("content") or ""))
        )
        assert nudge_count == 1  # 只注入一次

    async def test_no_declaration_no_interference(self, session, monkeypatch) -> None:
        """未声明 required_tools 的存量插件:行为不变,无注入。"""
        skill = _skill("skill:plain")
        await _register_rows(session, skill)
        from agentplatform.core.agent import loop as loop_mod

        async def _fake_skill(res, args, skill_call=None):
            return "ok"

        monkeypatch.setattr(loop_mod, "execute_skill", _fake_skill)
        client = _ScriptedClient(["CALL:skill__plain", "直接交付"])
        result = await run_agent(session, client, resource_ids=[skill.id],
                                 user_message="hi")
        assert "直接交付" in result.text
        assert all(
            not any("系统校验" in (m.get("content") or "") for m in msgs)
            for msgs in client.seen_prompts
        )
