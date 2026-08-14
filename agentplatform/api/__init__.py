"""API 路由聚合。

基础路径 /api(见 005 §1);错误统一为 {error: {code, message}}。
认证/对话/插件/注册表/LLM 端点子路由由对应里程碑挂载。
"""

from fastapi import APIRouter

from agentplatform.api import admin_llm, chat, health, plugins, registry

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(registry.router)
api_router.include_router(admin_llm.router)
api_router.include_router(plugins.router)
api_router.include_router(chat.router)
