"""新用户冷启动(产品打磨②):注册后预置引导,5 分钟内见到价值。

预置内容:
- 一条欢迎助手消息(平台能做什么+三个上手动作)
- 不建假数据(空列表/假文档会误导);引导指向真实动作
"""

WELCOME_BLOCKS: list[dict] = [
    {
        "type": "markdown",
        "data": {
            "text": (
                "👋 欢迎来到 AgentPlatform!\n\n"
                "我是平台向导。你可以直接和我对话——试试问我:**「帮我记一条待办:明天上午开会」**,"
                "或**「搜索一下今天 AI 领域的新闻」**。\n\n"
                "**三步上手**:\n"
                "1. 🏠 **工作台**(顶部切换)——待办、晨报、知识库动态都在那\n"
                "2. 📚 **知识库**——上传文档或配 GitHub/网页数据源,助手即可检索回答\n"
                "3. 🧩 **助手广场**——选用开发者发布的领域助手\n\n"
                "提示:对我说「记住我喜欢简洁的回答」,我会在后续所有对话中记得。"
            )
        },
    },
]


async def seed_onboarding(db, user_id: str) -> None:
    """注册后调用:创建向导会话与欢迎消息(失败静默,不阻塞注册)。"""
    try:
        from agentplatform.core.message.model import Message, MessageRole
        from agentplatform.core.session.service import create_session

        sess = await create_session(db, plugin_id=None, title="平台向导", user_id=str(user_id))
        db.add(Message(session_id=sess.id, role=MessageRole.assistant, blocks=WELCOME_BLOCKS))
        await db.flush()
    except Exception:  # noqa: BLE001  引导失败不影响注册
        pass
