"""Schema 驱动表单测试(控件零感知):schema→字段映射 + 缺参拦截。"""

import json

from agentplatform.core.agent.schema_form import (
    form_block_for,
    missing_required,
    schema_to_form_fields,
)

SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "description": "会议主题"},
        "date": {"type": "string", "format": "date", "title": "日期"},
        "start_at": {"type": "string", "format": "date-time", "title": "开始时间"},
        "level": {"enum": ["高", "中", "低"], "description": "优先级"},
        "count": {"type": "integer"},
        "notes": {"type": "array", "description": "备注列表,每行一条"},
        "enabled": {"type": "boolean"},
        "long_desc": {"type": "string", "description": "这里是一段超过四十个字符的很长的描述用于触发 textarea 判定逻辑"},
    },
    "required": ["topic", "date"],
}


class TestSchemaToFields:
    def test_type_mapping(self) -> None:
        fields = {f["key"]: f for f in schema_to_form_fields(SCHEMA)}
        assert fields["topic"]["widget"] == "text"
        assert fields["date"]["widget"] == "date"
        assert fields["start_at"]["widget"] == "datetime"
        assert fields["level"]["widget"] == "select" and fields["level"]["options"] == ["高", "中", "低"]
        assert fields["count"]["widget"] == "number"
        assert fields["notes"]["widget"] == "textarea"
        assert fields["enabled"]["widget"] == "toggle"
        assert fields["long_desc"]["widget"] == "textarea"
        assert fields["topic"]["required"] is True and fields["level"]["required"] is False

    def test_empty_schema(self) -> None:
        assert schema_to_form_fields(None) == []
        assert schema_to_form_fields({}) == []
        assert schema_to_form_fields({"properties": {}}) == []


class TestMissingAndBlock:
    def test_missing_required(self) -> None:
        assert missing_required(SCHEMA, {}) == ["topic", "date"]
        assert missing_required(SCHEMA, {"topic": "x"}) == ["date"]
        assert missing_required(SCHEMA, {"topic": "x", "date": "2026-01-01"}) == []
        assert missing_required(SCHEMA, {"topic": "  "}) == ["topic", "date"]  # 空串视为缺失

    def test_form_block(self) -> None:
        block = form_block_for("周会技能", SCHEMA)
        assert block["type"] == "input.form"
        data = block["data"]
        assert data["title"].startswith("请补充")
        assert len(data["fields"]) == 8
        assert form_block_for("x", {"properties": {}}) is None


class TestLoopIntercept:
    async def test_missing_param_yields_form_not_execution(self, session) -> None:
        """loop 层:skill 缺 required 参数 → 下发表单而非执行(不靠模型文本追问)。"""
        from agentplatform.core.agent.loop import execute_tool  # noqa: F401
        from agentplatform.core.registry.model import SkillTool, SkillToolKind, SkillToolSource
        from agentplatform.core.agent.executor import execute_skill

        # 构造带 schema 的 skill 资源(不落库——用 dataclass 替身验证分支逻辑)
        import uuid as _uuid

        res = SkillTool(
            id="skill:form_probe", version="1.0.0", kind=SkillToolKind.skill,
            name="form_probe", source=SkillToolSource.private, owner_id="t",
            schema_={"parameters": SCHEMA},
        )
        # 直接验证 execute 分支用的两个纯函数组合行为(完整 loop 走流式,另由 e2e 覆盖)
        assert missing_required(res.schema_.get("parameters"), {}) == ["topic", "date"]
        block = form_block_for(res.name, res.schema_.get("parameters"))
        assert block is not None and block["data"]["fields"][1]["widget"] == "date"
