"""Schema 驱动表单(控件零感知):skill 参数 schema → input.form 字段自动生成。

设计动机(用户核心诉求):写助手的人不应关注控件存在——作者只声明
"我需要什么数据"(skill schema,写 skill 时本来就要写),平台保证
"用户看到最合适的控件"(string→输入框/enum→下拉/date→日期控件),
控件决策不经过模型,确定性 100%。

链路:loop 检测 skill 调用缺 required 参数 → schema_to_form_fields 生成
input.form 下发 → interact 回填【表单提交】落会话 → 下一轮模型带值
调 skill,参数齐则执行。
"""

from typing import Any


def schema_to_form_fields(schema: dict | None) -> list[dict]:
    """JSON Schema properties → input.form 的扁平字段描述(经前端 normalizeFormField 渲染)。

    映射:string→input.text(textarea 标记/长 desc→textarea)、integer/number→
    input.number、enum→input.select(带 options)、format:date→input.date、
    boolean→input.toggle;required 列表逐项标必填。
    """
    if not isinstance(schema, dict):
        return []
    props = schema.get("properties") or {}
    if not isinstance(props, dict) or not props:
        return []
    required = set(schema.get("required") or [])

    fields: list[dict] = []
    for name, spec in props.items():
        if not isinstance(spec, dict):
            continue
        field: dict[str, Any] = {
            "key": str(name),
            "label": str(spec.get("title") or name),
            "required": name in required,
        }
        desc = spec.get("description")
        if desc:
            field["placeholder"] = str(desc)[:80]
        if spec.get("default") is not None:
            field["default"] = spec.get("default")

        enum_vals = spec.get("enum")
        if isinstance(enum_vals, list) and enum_vals:
            field["widget"] = "select"
            field["options"] = [str(v) for v in enum_vals]
        else:
            fmt = spec.get("format")
            ftype = spec.get("type")
            if fmt in ("date-time", "datetime"):
                field["widget"] = "datetime"
            elif fmt == "date":
                field["widget"] = "date"
            elif ftype in ("integer", "number"):
                field["widget"] = "number"
            elif ftype == "boolean":
                field["widget"] = "toggle"
            elif ftype == "array":
                field["widget"] = "textarea"
                field["placeholder"] = field.get("placeholder") or "每行一项"
            else:
                # 长描述/多行语义提示 → textarea,否则单行
                is_long = len(str(desc or "")) > 20 or "\n" in str(desc or "")
                field["widget"] = "textarea" if is_long else "text"
        fields.append(field)
    return fields


def missing_required(schema: dict | None, args: dict) -> list[str]:
    """返回 args 中缺失的 required 参数名。"""
    if not isinstance(schema, dict):
        return []
    out = []
    for name in schema.get("required") or []:
        v = args.get(name)
        if v is None or (isinstance(v, str) and not v.strip()):
            out.append(str(name))
    return out


def form_block_for(skill_name: str, schema: dict | None) -> dict | None:
    """生成收集缺失参数的 input.form ContentBlock;无字段需求返回 None。"""
    fields = schema_to_form_fields(schema)
    if not fields:
        return None
    return {
        "type": "input.form",
        "data": {
            "title": f"请补充「{skill_name}」所需信息",
            "description": "填写后助手将立即继续执行(表单由平台根据技能参数自动生成)",
            "fields": fields,
            "submit_text": "提交并继续",
            "action": "schema_form_submit",
        },
    }
