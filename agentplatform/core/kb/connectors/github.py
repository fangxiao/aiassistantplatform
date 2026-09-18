"""GitHub 连接器(M13 T13.8,设计 009 §3;需求 U7)。

Git Trees API 一次枚举全量文件树 → 按 路径前缀/后缀 过滤 → raw 逐个下载文本,
内容入库复用编排层 hash 幂等(未变更自动跳过,无需客户端记 SHA)。
凭据: PAT(credentials.token,密文存储);external_id = 文件路径。
"""

import json
import logging
from urllib.parse import quote

import httpx

from agentplatform.config import settings
from agentplatform.core.kb.connectors.base import FetchedDoc, FetchResult, register_adapter

logger = logging.getLogger(__name__)

_API = "https://api.github.com"
_DEFAULT_EXTENSIONS = [".md", ".markdown", ".txt", ".rst"]
_MAX_TREE_ENTRIES = 2000  # 单仓库文件数硬顶(防超大仓库拖垮同步)


def _headers(token: str) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": settings.connector_user_agent,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def fetch(
    config: dict,
    credentials: dict,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchResult:
    """GitHub 数据源抓取(全量型:枚举树 + 下载文本,编排层按 hash 幂等)。"""
    repo = str(config.get("repo") or "").strip()
    if not repo or repo.count("/") != 1:
        raise ValueError("GitHub 数据源必须配置 repo(owner/repo 格式)")
    branch = str(config.get("branch") or "main").strip()
    prefixes = tuple(str(p).strip("/") + "/" for p in (config.get("paths") or []) if str(p).strip())
    extensions = tuple(
        e.lower() if e.lower().startswith(".") else f".{e.lower()}"
        for e in (config.get("extensions") or _DEFAULT_EXTENSIONS)
    )
    token = str(credentials.get("token") or "")
    hard_cap = settings.connector_max_pages

    headers = _headers(token)
    async with httpx.AsyncClient(
        transport=transport,
        timeout=settings.connector_fetch_timeout_s,
        follow_redirects=True,
    ) as client:
        # 1. 一次拿全量文件树
        resp = await client.get(f"{_API}/repos/{repo}/git/trees/{quote(branch)}", params={"recursive": "1"}, headers=headers)
        if resp.status_code == 404:
            raise ValueError(f"仓库或分支不存在: {repo}@{branch}(检查名称与 token 权限)")
        if resp.status_code == 401:
            raise ValueError("GitHub 认证失败:token 无效或过期")
        resp.raise_for_status()
        tree = resp.json().get("tree", [])

        # 2. 过滤:blob + 路径前缀 + 后缀 + 大小
        candidates = [
            entry
            for entry in tree
            if entry.get("type") == "blob"
            and (not prefixes or any(entry["path"].startswith(p) for p in prefixes))
            and entry["path"].lower().endswith(extensions)
            and (entry.get("size") or 0) <= settings.connector_max_page_bytes
        ][: min(_MAX_TREE_ENTRIES, hard_cap)]

        # 3. 逐个下载文本(单文件失败不中断,验收 8)
        docs: list[FetchedDoc] = []
        for entry in candidates:
            path = entry["path"]
            try:
                raw = await client.get(
                    f"{_API}/repos/{repo}/contents/{quote(path)}",
                    params={"ref": branch},
                    headers={**headers, "Accept": "application/vnd.github.raw"},
                )
                if raw.status_code != 200:
                    logger.warning("connector-github: 下载失败 %s: %s", path, raw.status_code)
                    continue
                text = raw.text
                if not text.strip():
                    continue
                filename = path.rsplit("/", 1)[-1]
                docs.append(
                    FetchedDoc(
                        external_id=path,
                        url=f"https://github.com/{repo}/blob/{branch}/{path}",
                        title=filename,
                        content_markdown=text,
                        mime="text/markdown" if path.lower().endswith((".md", ".markdown")) else "text/plain",
                    )
                )
            except Exception as exc:  # noqa: BLE001  单文件失败不中断(验收 8)
                logger.warning("connector-github: 下载异常 %s: %s", path, exc)

    return FetchResult(docs=docs, full=True)


register_adapter("github", fetch)
