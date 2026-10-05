"""交付物登记服务(M25/设计 019 §3)。

所有登记入口 try/except 包裹——埋点失败仅日志,绝不影响工具原返回/任务产出
(需求 014 A2 闭环自愈)。
"""

import logging
import re
import uuid
from urllib.parse import parse_qs, urlparse

from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# 产生可登记文件产物的工具 → kind 映射(设计 019 §3.1 白名单)
TOOL_KIND_MAP = {
    "tool:image_gen": "image",
    "tool:html_render": "html",
}

_TITLE_STRIP_TAGS = re.compile(r"<[^>]+>")


def extract_file_path(url: str) -> str | None:
    """从签名 URL(/api/files/raw?path=...&sig=...,可带公网前缀)提取相对 path。"""
    try:
        q = parse_qs(urlparse(url).query)
        path = (q.get("path") or [None])[0]
        return path or None
    except Exception:  # noqa: BLE001
        return None


def derive_title(tool_id: str, args: dict) -> str:
    """展示名:image 取 prompt;html 取去标签正文;兜底工具名。截断 40 字。"""
    raw = ""
    if "prompt" in args and isinstance(args["prompt"], str):
        raw = args["prompt"]
    elif "html" in args and isinstance(args["html"], str):
        raw = _TITLE_STRIP_TAGS.sub(" ", args["html"])
    raw = " ".join(raw.split()).strip()
    if not raw:
        raw = tool_id.split(":", 1)[-1]
    return raw[:40]


async def register_tool_artifact(
    session: AsyncSession,
    *,
    tool_id: str,
    result: str,
    args: dict,
    owner_id: str | None,
    chat_session_id: str | None,
) -> None:
    """loop 工具结果回流埋点:白名单工具从结果 URL 提取 path 登记。

    任何异常静默(仅日志)——闭环自愈。
    """
    try:
        kind = TOOL_KIND_MAP.get(tool_id)
        if kind is None or not owner_id or not result:
            return
        from agentplatform.core.artifacts.model import Artifact

        for url in set(re.findall(r'https?://[^\s"<>]+|/api/files/raw\?[^\s"<>]+', result)):
            path = extract_file_path(url)
            if not path:
                continue
            session.add(
                Artifact(
                    user_id=uuid.UUID(owner_id),
                    session_id=uuid.UUID(chat_session_id) if chat_session_id else None,
                    kind=kind,
                    title=derive_title(tool_id, args if isinstance(args, dict) else {}),
                    path=path,
                )
            )
        await session.flush()
    except Exception:
        log.warning("交付物登记失败 tool=%s", tool_id, exc_info=True)


async def register_task_report(
    session: AsyncSession,
    *,
    owner_id: str,
    title: str,
    chat_session_id: str | None,
    task_run_id: str | None,
) -> None:
    """定时任务成功产出登记(kind=report,凭双引用跳会话;设计 019 §3.2)。"""
    try:
        from agentplatform.core.artifacts.model import Artifact

        session.add(
            Artifact(
                user_id=uuid.UUID(owner_id),
                session_id=uuid.UUID(chat_session_id) if chat_session_id else None,
                task_run_id=uuid.UUID(task_run_id) if task_run_id else None,
                kind="report",
                title=title[:80],
            )
        )
        await session.flush()
    except Exception:
        log.warning("定时任务交付物登记失败 title=%s", title, exc_info=True)
