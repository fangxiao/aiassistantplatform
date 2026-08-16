"""平台共享能力全景清单 (Skill / Tool / 22 种富交互 ContentBlock 控件)。

供 API / CLI / 前端 / 文档统一复用。
"""

from __future__ import annotations

from typing import Any

from agentplatform.core.registry.builtin import ALL as BUILTIN_RESOURCES

# 22 种富交互组件定义与示例
CONTENT_BLOCKS_CATALOG: list[dict[str, Any]] = [
    # 1. 展示类 (8 种)
    {
        "type": "markdown",
        "category": "display",
        "category_name": "展示类",
        "name": "Markdown 文本",
        "description": "富文本排版，支持标题、列表、粗斜体、引用及内联链接",
        "sample_data": {
            "markdown": "### 🎯 评审概览\n该 PRD **结构完整**，核心链路清晰。\n- 建议补充异常分支处理\n- 建议明确响应超时阈值"
        },
        "python_snippet": '{"type": "markdown", "data": {"markdown": "### 评审结论\\n完整度评分: **90分**"}}',
    },
    {
        "type": "code",
        "category": "display",
        "category_name": "展示类",
        "name": "代码块",
        "description": "多语言语法高亮代码块，内置一键复制代码按钮",
        "sample_data": {
            "language": "python",
            "code": "def evaluate_prd(doc: str) -> dict:\n    return {'score': 90, 'status': 'PASS'}",
        },
        "python_snippet": '{"type": "code", "data": {"language": "python", "code": "# 生成的配置\\nDEBUG=True"}}',
    },
    {
        "type": "table",
        "category": "display",
        "category_name": "展示类",
        "name": "结构化表格",
        "description": "多列结构化数据表格，支持前端列排序与美化排版",
        "sample_data": {
            "columns": ["评审维度", "得分", "评级", "主要建议"],
            "rows": [
                ["功能完整性", "92", "优秀", "无明显缺失"],
                ["技术可行性", "85", "良好", "关注并发性能"],
                ["安全与合规", "78", "中等", "需补齐权限校验"],
            ],
        },
        "python_snippet": '{"type": "table", "data": {"columns": ["维度", "得分"], "rows": [["完整性", "90"], ["可行性", "85"]]}}',
    },
    {
        "type": "card",
        "category": "display",
        "category_name": "展示类",
        "name": "卡片容器",
        "description": "结构化卡片容器，支持标题、说明及内嵌子组件",
        "sample_data": {
            "title": "📋 核心评审结论",
            "description": "综合评分 A 级（建议进入技术评审阶段）",
            "blocks": [
                {
                    "type": "markdown",
                    "data": {"markdown": "**发布建议**：建议在补充鉴权设计后准予排期。"},
                }
            ],
        },
        "python_snippet": '{"type": "card", "data": {"title": "结果概览", "description": "通过", "blocks": []}}',
    },
    {
        "type": "collapsible",
        "category": "display",
        "category_name": "展示类",
        "name": "折叠面板",
        "description": "可展开/折叠面板，用于收纳冗长日志、排查明细或技术细则",
        "sample_data": {
            "title": "🔍 点击查看 12 条风险排查详细日志",
            "default_open": False,
            "blocks": [
                {
                    "type": "markdown",
                    "data": {
                        "markdown": "1. 接口未做限流拦截\n2. 缺少幂等 Token 机制\n3. 缓存穿透无降级策略"
                    },
                }
            ],
        },
        "python_snippet": '{"type": "collapsible", "data": {"title": "详细日志", "default_open": False, "blocks": []}}',
    },
    {
        "type": "image",
        "category": "display",
        "category_name": "展示类",
        "name": "图片展示",
        "description": "安全图片渲染，支持图片标题、Alt 描述与全屏预览放大",
        "sample_data": {
            "url": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80",
            "alt": "架构示意图",
            "caption": "微服务时序调用架构示意图",
        },
        "python_snippet": '{"type": "image", "data": {"url": "https://example.com/pic.png", "alt": "图表", "caption": "图表说明"}}',
    },
    {
        "type": "file",
        "category": "display",
        "category_name": "展示类",
        "name": "文件附件",
        "description": "文件下载与预览条目，展示文件名、格式图标与文件体积",
        "sample_data": {
            "name": "PRD_Review_Report_2026.pdf",
            "url": "/downloads/prd_report.pdf",
            "size": "2.4 MB",
        },
        "python_snippet": '{"type": "file", "data": {"name": "report.pdf", "url": "/download/report.pdf", "size": "1.2MB"}}',
    },
    {
        "type": "mermaid",
        "category": "display",
        "category_name": "展示类",
        "name": "Mermaid 流程图",
        "description": "流程图、时序图、甘特图等动态可视化渲染",
        "sample_data": {
            "code": "graph TD;\n  A[📄 提交 PRD] --> B[🤖 AI 智能解析];\n  B --> C{是否合规?};\n  C -->|是| D[✅ 输出评审打分卡];\n  C -->|否| E[⚠️ 弹出修改确认表单];"
        },
        "python_snippet": '{"type": "mermaid", "data": {"code": "graph TD; A-->B; B-->C;"}}',
    },
    # 2. 交互输入类 (11 种)
    {
        "type": "input.text",
        "category": "interactive",
        "category_name": "交互输入类",
        "name": "单行文本输入框",
        "description": "向用户采集单行文本信息（如功能名称、关键字、邮箱）",
        "sample_data": {
            "id": "feature_name",
            "label": "补充功能模块名称",
            "placeholder": "例如：用户积分商城",
        },
        "python_snippet": '{"type": "input.text", "data": {"id": "username", "label": "用户名", "placeholder": "请输入"}}',
    },
    {
        "type": "input.textarea",
        "category": "interactive",
        "category_name": "交互输入类",
        "name": "多行长文本输入框",
        "description": "采集多行需求描述、评审意见或备注说明",
        "sample_data": {
            "id": "adjust_notes",
            "label": "补充说明与调整建议",
            "placeholder": "请详细描述您希望智能体关注的特定技术指标或业务场景...",
            "rows": 3,
        },
        "python_snippet": '{"type": "input.textarea", "data": {"id": "desc", "label": "需求描述", "rows": 3}}',
    },
    {
        "type": "input.number",
        "category": "interactive",
        "category_name": "交互输入类",
        "name": "数字微调输入框",
        "description": "采集数值类参数，支持上下限与步长控制",
        "sample_data": {
            "id": "target_score",
            "label": "目标期望评分阈值 (分)",
            "min": 60,
            "max": 100,
            "default": 85,
        },
        "python_snippet": '{"type": "input.number", "data": {"id": "count", "label": "迭代周期(天)", "default": 14, "min": 1}}',
    },
    {
        "type": "input.select",
        "category": "interactive",
        "category_name": "交互输入类",
        "name": "下拉选择框",
        "description": "单选下拉选择，适合候选项较多时的空间优化",
        "sample_data": {
            "id": "review_role",
            "label": "当前评审视角",
            "options": [
                {"label": "👑 业务产品经理 (重视业务价值与转化)", "value": "pm"},
                {"label": "💻 架构师 (重视高可用与技术债)", "value": "architect"},
                {"label": "🛡️ 安全合规专家 (重视数据安全与合规)", "value": "security"},
            ],
        },
        "python_snippet": '{"type": "input.select", "data": {"id": "role", "label": "角色", "options": [{"label": "专家", "value": "exp"}]}}',
    },
    {
        "type": "input.radio",
        "category": "interactive",
        "category_name": "交互输入类",
        "name": "单选按钮组",
        "description": "平铺式单选项，适合候选项较少（2-4个）时直观呈现",
        "sample_data": {
            "id": "priority_level",
            "label": "项目优先级定级",
            "options": [
                {"label": "🔥 紧急 (P0)", "value": "P0"},
                {"label": "⚡ 高优 (P1)", "value": "P1"},
                {"label": "☕ 常规 (P2)", "value": "P2"},
            ],
        },
        "python_snippet": '{"type": "input.radio", "data": {"id": "env", "label": "环境", "options": [{"label": "生产", "value": "prod"}]}}',
    },
    {
        "type": "input.checkbox",
        "category": "interactive",
        "category_name": "交互输入类",
        "name": "多选复选框组",
        "description": "支持用户勾选多项属性或功能清单",
        "sample_data": {
            "id": "focus_dimensions",
            "label": "选择本次重点关注的维度",
            "options": [
                {"label": "需求完备度", "value": "completeness"},
                {"label": "性能与并发", "value": "performance"},
                {"label": "异常与容灾", "value": "resilience"},
                {"label": "用户交互体验", "value": "ux"},
            ],
        },
        "python_snippet": '{"type": "input.checkbox", "data": {"id": "tags", "label": "标签", "options": [{"label": "A", "value": "a"}]}}',
    },
    {
        "type": "input.toggle",
        "category": "interactive",
        "category_name": "交互输入类",
        "name": "开关切换器",
        "description": "二元状态开关（开/关、启用/禁用、包含/排除）",
        "sample_data": {
            "id": "enable_deep_audit",
            "label": "开启大模型深度对抗式审查",
            "default": True,
        },
        "python_snippet": '{"type": "input.toggle", "data": {"id": "auto_save", "label": "自动保存", "default": True}}',
    },
    {
        "type": "input.date",
        "category": "interactive",
        "category_name": "交互输入类",
        "name": "日期选择器",
        "description": "标准日期/截止时间选择控件",
        "sample_data": {
            "id": "deadline",
            "label": "期望评审报告提交截止日期",
        },
        "python_snippet": '{"type": "input.date", "data": {"id": "target_date", "label": "目标发布日期"}}',
    },
    {
        "type": "input.file",
        "category": "interactive",
        "category_name": "交互输入类",
        "name": "文件上传组件",
        "description": "允许用户在对话流中直接上传补充文件或数据包",
        "sample_data": {
            "id": "attachment",
            "label": "上传待评审 PRD 文档 (支持 .pdf, .docx, .md)",
            "accept": ".pdf,.docx,.md",
        },
        "python_snippet": '{"type": "input.file", "data": {"id": "doc_file", "label": "上传文件", "accept": ".pdf"}}',
    },
    {
        "type": "input.confirm",
        "category": "interactive",
        "category_name": "交互输入类",
        "name": "确认操作框",
        "description": "包含确认与取消双动作的操作确认框，点击后触发后端回调",
        "sample_data": {
            "text": "已生成针对该 PRD 的 3 条高危风险整改方案，是否确认一键创建 Jira 缺陷单？",
            "action": "create_jira_tickets",
            "confirm_text": "🚀 确认创建",
            "cancel_text": "稍后手动处理",
        },
        "python_snippet": '{"type": "input.confirm", "data": {"text": "确认导出?", "action": "export_action", "confirm_text": "确认"}}',
    },
    {
        "type": "input.form",
        "category": "interactive",
        "category_name": "交互输入类",
        "name": "复合表单",
        "description": "集成多个字段的统一提交表单，支持整体校验与一次性回传",
        "sample_data": {
            "title": "📝 PRD 终审决议表单",
            "action": "submit_final_review",
            "submit_text": "提交终审记录",
            "fields": [
                {
                    "id": "verdict",
                    "label": "终审结论",
                    "type": "select",
                    "options": [
                        {"label": "✅ 准予立项上线", "value": "pass"},
                        {"label": "⚠️ 需补充设计后复审", "value": "re_review"},
                        {"label": "❌ 驳回立项", "value": "reject"},
                    ],
                },
                {
                    "id": "expert_comment",
                    "label": "专家总评与补充意见",
                    "type": "textarea",
                },
            ],
        },
        "python_snippet": '{"type": "input.form", "data": {"title": "表单", "action": "submit_act", "submit_text": "提交", "fields": []}}',
    },
    # 3. 反馈动作类 (3 种)
    {
        "type": "action.copy",
        "category": "action",
        "category_name": "反馈动作类",
        "name": "一键复制按钮",
        "description": "点击一键将大段格式化文本或代码拷贝到系统剪贴板",
        "sample_data": {
            "text": "curl -X POST http://localhost:8000/api/chat/sessions -H 'Content-Type: application/json' -d '{\"message\":\"hello\"}'",
            "label": "📋 复制完整 cURL 请求",
        },
        "python_snippet": '{"type": "action.copy", "data": {"text": "需要复制的内容", "label": "复制"}}',
    },
    {
        "type": "action.thumbs",
        "category": "action",
        "category_name": "反馈动作类",
        "name": "点赞点踩反馈",
        "description": "针对单条回答进行点赞 (up) 或点踩 (down) 反馈打标",
        "sample_data": {
            "action": "feedback_vote",
            "target_id": "review_block_001",
        },
        "python_snippet": '{"type": "action.thumbs", "data": {"action": "thumb_feedback", "target_id": "msg-1"}}',
    },
    {
        "type": "action.regenerate",
        "category": "action",
        "category_name": "反馈动作类",
        "name": "重新生成按钮",
        "description": "引导用户或触发助手重新换个思路或深度重新生成结果",
        "sample_data": {
            "action": "re_evaluate_prd",
            "label": "🔄 换个专家视角重新评审",
        },
        "python_snippet": '{"type": "action.regenerate", "data": {"action": "retry_action", "label": "重新生成"}}',
    },
]


def get_capabilities_manifest() -> dict[str, Any]:
    """返回全量平台共享能力清单 (Skill/Tool + 22 种 ContentBlock 控件)。"""
    skills = [r for r in BUILTIN_RESOURCES if r["kind"] == "skill"]
    tools = [r for r in BUILTIN_RESOURCES if r["kind"] == "tool"]

    return {
        "platform": "AgentPlatform",
        "version": "1.0.0",
        "summary": {
            "builtin_skills_count": len(skills),
            "builtin_tools_count": len(tools),
            "content_blocks_count": len(CONTENT_BLOCKS_CATALOG),
        },
        "builtin_skills": [
            {
                "id": s["id"],
                "name": s["name"],
                "version": s["version"],
                "description": s["description"],
                "schema": s["schema"],
                "dependency_example": f"- {s['id']}@^{s['version']}",
            }
            for s in skills
        ],
        "builtin_tools": [
            {
                "id": t["id"],
                "name": t["name"],
                "version": t["version"],
                "description": t["description"],
                "schema": t["schema"],
                "dependency_example": f"- {t['id']}@^{t['version']}",
            }
            for t in tools
        ],
        "content_blocks": CONTENT_BLOCKS_CATALOG,
    }
