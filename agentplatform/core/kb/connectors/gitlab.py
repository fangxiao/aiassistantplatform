"""GitLab 连接器(自托管,API v4)——离职知识归档/内网代码文档同步。

与 GitHub adapter 同构:trees 枚举 + raw 下载,内容 hash 幂等;
差异仅 API 形态:项目以 `owner/repo` 路径段访问,header 用
`PRIVATE-TOKEN`(兼容 Bearer),raw 走 /raw 端点。
支持 base_url 指向内网自托管实例(平台与 GitLab 同网即可)。
"""

import logging
from urllib.parse import quote

import httpx

from agentplatform.config import settings
from agentplatform.core.kb.connectors.base import FetchedDoc, FetchResult, register_adapter

logger = logging.getLogger(__name__)

_DEFAULT_EXTENSIONS = [".md", ".markdown", ".txt", ".rst"]
_MAX_TREE_ENTRIES = 2000


def _headers(token: str) -> dict[str, str]:
    headers = {
        "User-Agent": settings.connector_user_agent,
    }
    if token:
        # 自托管 GitLab 常配 PRIVATE-TOKEN;云版/新版兼容 Bearer
        headers["PRIVATE-TOKEN"] = token
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _project_path(repo: str) -> str:
    """owner/repo → URL 编码的项目路径(GitLab v4 要求 path 参数编码)。"""
    return quote(repo.strip().strip("/"), safe="")


async def fetch(
    config: dict,
    credentials: dict,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchResult:
    """GitLab 数据源抓取(全量型):树枚举 + raw 逐文件下载。

    config: {base_url, repo("group/project"), branch(默认 main), paths(前缀白名单),
    extensions(默认 md/txt/rst)}
    credentials: {token}(GitLab PAT,可空=公开项目)
    """
    base_url = str(config.get("base_url") or "").strip().rstrip("/")
    repo = str(config.get("repo") or "").strip()
    if not base_url or repo.count("/") < 1:
        raise ValueError("GitLab 数据源必须配置 base_url 与 repo(group/project)")
    branch = str(config.get("branch") or "main").strip()
    prefixes = tuple(str(p).strip("/") + "/" for p in (config.get("paths") or []) if str(p).strip())
    extensions = tuple(
        e.lower() if e.lower().startswith(".") else f".{e.lower()}"
        for e in (config.get("extensions") or _DEFAULT_EXTENSIONS)
    )
    token = str(credentials.get("token") or "")
    headers = _headers(token)
    proj = _project_path(repo)

    async with httpx.AsyncClient(
        transport=transport, timeout=settings.connector_fetch_timeout_s, follow_redirects=True
    ) as client:
        # 1. 树枚举(recursive)
        tree: list[dict] = []
        for page in range(1, 21):  # 20 页 × 100 = 2000 条上限,防超大仓库
            r = await client.get(
                f"{base_url}/api/v4/projects/{proj}/repository/tree",
                params={"ref": branch, "recursive": "true", "per_page": 100, "page": page},
                headers=headers,
            )
            if r.status_code == 404:
                raise ValueError(f"项目或分支不存在: {repo}@{branch}(检查路径与 token 权限)")
            if r.status_code == 401:
                raise ValueError("GitLab 认证失败:token 无效")
            if r.status_code != 200:
                break
            batch = r.json()
            tree.extend(batch)
            if len(batch) < 100:  # 不足一页即最后一页
                break

        candidates = [
            e for e in tree
            if e.get("type") == "blob"
            and (not prefixes or any(e["path"].startswith(p) for p in prefixes))
            and e["path"].lower().endswith(extensions)
            and (e.get("size") or 0) <= settings.connector_max_page_bytes
        ][:_MAX_TREE_ENTRIES]

        docs: list[FetchedDoc] = []
        for entry in candidates:
            path = entry["path"]
            try:
                raw = await client.get(
                    f"{base_url}/api/v4/projects/{proj}/repository/files/{quote(path, safe='')}/raw",
                    params={"ref": branch},
                    headers=headers,
                )
                if raw.status_code != 200:
                    logger.warning("connector-gitlab: 下载失败 %s: %s", path, raw.status_code)
                    continue
                text = raw.text
                if not text.strip():
                    continue
                filename = path.rsplit("/", 1)[-1]
                docs.append(
                    FetchedDoc(
                        external_id=path,
                        url=f"{base_url}/{repo.strip('/')}/-/blob/{branch}/{path}",
                        title=filename,
                        content_markdown=text,
                        mime="text/markdown" if path.lower().endswith((".md", ".markdown")) else "text/plain",
                    )
                )
            except Exception as exc:  # noqa: BLE001  单文件失败不中断
                logger.warning("connector-gitlab: 下载异常 %s: %s", path, exc)

    return FetchResult(docs=docs, full=True)


register_adapter("gitlab", fetch)
