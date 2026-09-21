"""内容型连接器测试(M13,T13.7;需求 006 验收 1/2/4/5/7/8 覆盖)。

- web adapter 单测:SSRF 拦截/同域过滤/markdown 转换/页数上限/robots(MockTransport)
- 编排幂等:_apply_result 新增/跳过/更新/删除/超限(测试 session,假 adapter)
- 调度:is_due 纯函数
- API 集成:鉴权/校验/202 触发/凭据不回显
"""

import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from agentplatform.config import settings
from agentplatform.core.auth.model import UserRole
from agentplatform.core.auth.service import create_user
from agentplatform.core.kb.connectors import base as connector_base
from agentplatform.core.kb.connectors import service as connector_service
from agentplatform.core.kb.connectors.base import FetchedDoc, FetchResult
from agentplatform.core.kb.connectors.scheduler import is_due
from agentplatform.core.kb.connectors.web import fetch as web_fetch
from agentplatform.core.kb.model import (
    KbDataSource,
    KbDataSourceType,
    KbDocument,
    KbDocumentStatus,
)
from agentplatform.core.kb.service import KbError, create_kb
from agentplatform.core.registry.builtin.html_cleaner import run as html_cleaner_run


@pytest.fixture
async def dev_user(session: AsyncSession):
    return await create_user(session, f"cdev-{uuid.uuid4()}@test.dev", "password123", UserRole.developer)


@pytest.fixture
async def normal_user(session: AsyncSession):
    return await create_user(session, f"cu-{uuid.uuid4()}@test.dev", "password123", UserRole.user)

PAGE_A = """
<html><head><title>页面A</title></head><body>
<h1>标题A</h1><p>这是页面 A 的正文内容,足够长以通过切分。</p>
<a href="/b">同域链接</a><a href="https://other.example.org/x">外域链接</a>
</body></html>
"""
PAGE_B = "<html><head><title>页面B</title></head><body><p>页面 B 正文,含关键词向量检索。</p></body></html>"


def _mock_transport(pages: dict[str, str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url).rstrip("/")
        body = pages.get(url)
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _fake_dns(monkeypatch):
    """MockTransport 只 mock HTTP;DNS 解析替换为公网 IP,跳过真实解析。"""
    from agentplatform.core.kb.connectors import web as web_module

    async def fake_resolve(host: str) -> list[str]:
        return ["93.184.216.34"]

    monkeypatch.setattr(web_module, "_resolve_host", fake_resolve)


class TestWebAdapter:
    async def test_fetch_same_domain_and_markdown(self) -> None:
        """验收 1:种子页抓取 + 同域跟随;外域不跟。"""
        base = "https://docs.example.com"
        result = await web_fetch(
            {"urls": [f"{base}/a"], "max_depth": 1, "max_pages": 5, "respect_robots": False},
            {},
            transport=_mock_transport({f"{base}/a": PAGE_A, f"{base}/b": PAGE_B}),
        )
        assert result.full is True
        assert [d.external_id for d in result.docs] == [f"{base}/a", f"{base}/b"]
        a = result.docs[0]
        assert a.title == "页面A"
        assert "标题A" in a.content_markdown

    async def test_ssrf_blocked(self) -> None:
        """SSRF:回环/链路本地(云元数据)/内网/非 http 协议一律拦截。"""
        for url in (
            "http://127.0.0.1/secret",
            "http://169.254.169.254/latest/meta-data/",
            "http://192.168.1.10/admin",
            "ftp://example.com/file",
        ):
            result = await web_fetch({"urls": [url], "max_depth": 0}, {}, transport=_mock_transport({}))
            assert result.docs == [], url

    async def test_max_pages_cap(self) -> None:
        base = "https://cap.example.com"
        pages = {f"{base}/p{i}": f"<html><body><a href='/p{i+1}'>next</a>第{i}页</body></html>" for i in range(10)}
        result = await web_fetch(
            {"urls": [f"{base}/p0"], "max_depth": 5, "max_pages": 3, "respect_robots": False},
            {},
            transport=_mock_transport(pages),
        )
        assert len(result.docs) <= 3

    async def test_robots_disallow_skipped(self) -> None:
        """robots.txt Disallow:页面不抓(默认遵循,需求 U10)。"""
        base = "https://robot.example.com"
        robots = "User-agent: *\nDisallow: /private\n"
        pages = {f"{base}/robots.txt": robots, f"{base}/private/x": PAGE_B}

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/robots.txt":
                return httpx.Response(200, text=robots)
            body = pages.get(str(request.url).rstrip("/"))
            return httpx.Response(200, text=body or "miss", headers={"content-type": "text/html"})

        result = await web_fetch(
            {"urls": [f"{base}/private/x"], "max_depth": 0, "respect_robots": True},
            {},
            transport=httpx.MockTransport(handler),
        )
        assert result.docs == []


class FakeSource:
    """不落库的编排测试桩(仅用到 type/id/kb_id)。"""

    def __init__(self, kb_id: uuid.UUID) -> None:
        self.id = uuid.uuid4()
        self.kb_id = kb_id
        self.type = KbDataSourceType.web


@pytest.mark.asyncio
class TestOrchestration:
    async def _make_kb(self, session: AsyncSession, owner) -> object:
        return await create_kb(
            session, name=f"conn_{uuid.uuid4().hex[:8]}", slug=f"conn_{uuid.uuid4().hex[:8]}",
            owner=owner,
        )

    async def test_first_sync_and_idempotent(self, session: AsyncSession, dev_user) -> None:
        """验收 2 前半:首同步 added;同内容重跑 skipped(不重复建档)。"""
        kb = await self._make_kb(session, dev_user)
        source = FakeSource(kb.id)
        docs = [
            FetchedDoc(external_id="https://x.example.com/1", url="https://x.example.com/1",
                       title="文档一", content_markdown="# 文档一\n" + "内容" * 60),
            FetchedDoc(external_id="https://x.example.com/2", url="https://x.example.com/2",
                       title="文档二", content_markdown="# 文档二\n" + "其他" * 60),
        ]
        stats = await connector_service._apply_result(
            session, source, FetchResult(docs=docs, full=True)
        )
        assert stats == {"added": 2, "updated": 0, "deleted": 0, "skipped": 0, "failed_docs": 0}

        stats2 = await connector_service._apply_result(
            session, source, FetchResult(docs=docs, full=True)
        )
        assert stats2["skipped"] == 2 and stats2["added"] == 0

        rows = list(await session.scalars(
            __import__("sqlalchemy").select(KbDocument).where(KbDocument.data_source_id == source.id)
        ))
        assert len(rows) == 2
        assert all(r.origin == "connector" and r.source_app == "web" for r in rows)
        assert all(r.external_url for r in rows)

    async def test_update_and_deletion(self, session: AsyncSession, dev_user) -> None:
        """验收 2 后半:内容变更 → updated 重入 pipeline;外部删除 → 软删。"""
        kb = await self._make_kb(session, dev_user)
        source = FakeSource(kb.id)
        d1 = FetchedDoc("ext-1", "https://y.example.com/1", "保留", "# 保留\n" + "原文" * 60)
        d2 = FetchedDoc("ext-2", "https://y.example.com/2", "变更", "# 变更\n" + "旧文" * 60)
        await connector_service._apply_result(session, source, FetchResult(docs=[d1, d2], full=True))

        # 第二次:ext-1 内容变更(updated),ext-2 未变(skipped)
        d1_v2 = FetchedDoc("ext-1", "https://y.example.com/1", "保留", "# 保留\n" + "新版内容" * 60)
        stats = await connector_service._apply_result(
            session, source, FetchResult(docs=[d1_v2, d2], full=True)
        )
        assert stats["updated"] == 1 and stats["skipped"] == 1

        # 第三次:ext-2 从外部消失 → 软删(deleted)
        stats2 = await connector_service._apply_result(
            session, source, FetchResult(docs=[d1_v2], full=True)
        )
        assert stats2["deleted"] == 1
        from sqlalchemy import select as _sel

        remaining = list(await session.scalars(
            _sel(KbDocument).where(
                KbDocument.data_source_id == source.id,
                KbDocument.status != KbDocumentStatus.deleted,
            )
        ))
        assert [r.external_id for r in remaining] == ["ext-1"]

    async def test_quota_skip_not_abort(self, session: AsyncSession, dev_user, monkeypatch) -> None:
        """验收 7/8:达单库文档上限的文档计 failed_docs,不中断整次同步。"""
        kb = await self._make_kb(session, dev_user)
        monkeypatch.setattr(settings, "kb_max_documents_per_kb", 1)
        source = FakeSource(kb.id)
        docs = [
            FetchedDoc(f"ext-{i}", f"https://z.example.com/{i}", f"文档{i}", f"# {i}\n" + "内容" * 60)
            for i in range(3)
        ]
        stats = await connector_service._apply_result(session, source, FetchResult(docs=docs, full=True))
        assert stats["added"] == 1 and stats["failed_docs"] == 2


class TestScheduler:
    def test_is_due_semantics(self) -> None:
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        base = KbDataSource(
            id=uuid.uuid4(), kb_id=uuid.uuid4(), type=KbDataSourceType.web,
            name="s", config={}, poll_interval_minutes=60, status="active",
        )
        base.last_sync_at = None
        assert is_due(base, now)  # 从未同步 → due
        base.last_sync_at = now - timedelta(minutes=30)
        assert not is_due(base, now)  # 未到 60 分钟
        base.last_sync_at = now - timedelta(minutes=61)
        assert is_due(base, now)
        base.status = "disabled"
        assert not is_due(base, now)  # 停用不调度
        base.status = "active"
        base.poll_interval_minutes = None
        assert not is_due(base, now)  # 仅手动


@pytest.mark.asyncio
class TestSourcesApi:
    async def _kb(self, client, user_token_headers, visibility="private") -> str:
        r = await client.post(
            "/api/kb/kbs",
            json={"name": "conn-api", "slug": f"connapi{uuid.uuid4().hex[:8]}", "visibility": visibility},
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    async def test_source_lifecycle(self, client, session) -> None:
        kb_id = await self._kb(client, None)
        # 创建(web,缺 urls → 400)
        r = await client.post(f"/api/kb/kbs/{kb_id}/sources", json={"type": "web", "name": "s1", "config": {}})
        assert r.status_code == 400
        r = await client.post(
            f"/api/kb/kbs/{kb_id}/sources",
            json={"type": "web", "name": "文档站", "config": {"urls": ["https://docs.example.com/"]}, "poll_interval_minutes": 60},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["type"] == "web" and body["last_status"] == "never"
        sid = body["id"]

        # 未知类型 → 400
        r = await client.post(f"/api/kb/kbs/{kb_id}/sources", json={"type": "nope", "name": "x", "config": {}})
        assert r.status_code == 400

        # 触发同步 → 202(fake adapter:立即完成一次空抓)
        original = connector_base.ADAPTERS.get("web")

        async def fake_fetch(config, credentials, *, transport=None):
            return FetchResult(docs=[], full=True)

        connector_base.ADAPTERS["web"] = fake_fetch
        try:
            r = await client.post(f"/api/kb/kbs/{kb_id}/sources/{sid}/sync")
            assert r.status_code == 202, r.text
            run_id = r.json()["run_id"]
            # 后台 _run_sync 连的是运行库(测试库之外),不等待其完成;仅验证接口语义
            r2 = await client.get(f"/api/kb/kbs/{kb_id}/sources/{sid}/runs")
            assert r2.status_code == 200
            assert any(run["id"] == run_id for run in r2.json())
        finally:
            if original is not None:
                connector_base.ADAPTERS["web"] = original

        # 删除 → 204,列表空
        r = await client.delete(f"/api/kb/kbs/{kb_id}/sources/{sid}")
        assert r.status_code == 204
        r = await client.get(f"/api/kb/kbs/{kb_id}/sources")
        assert r.json() == []

    async def test_credentials_not_echoed(self, client) -> None:
        """验收 5:凭据密文存储,任何响应不回显。"""
        kb_id = await self._kb(client, None)
        r = await client.post(
            f"/api/kb/kbs/{kb_id}/sources",
            json={"type": "web", "name": "s", "config": {"urls": ["https://a.example.com/"]},
                  "credentials": {"token": "super-secret"}},
        )
        assert r.status_code == 201
        assert "super-secret" not in r.text
        listed = await client.get(f"/api/kb/kbs/{kb_id}/sources")
        assert "super-secret" not in listed.text

    async def test_private_kb_other_user_404(self, client, session, normal_user) -> None:
        """他人 private 库:不可见即无管理权 → 404。"""
        kb = await create_kb(
            session, name="other", slug=f"other{uuid.uuid4().hex[:8]}", owner=normal_user
        )
        await session.commit()
        r = await client.post(
            f"/api/kb/kbs/{kb.id}/sources",
            json={"type": "web", "name": "x", "config": {"urls": ["https://a.example.com/"]}},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_html_cleaner_produces_markdown_for_connector():
    """网页 adapter 依赖的 html_cleaner:标题与正文转 markdown(复用同一实现)。"""
    import json as _json

    out = _json.loads(html_cleaner_run(PAGE_A, extract_tables=False))
    assert out["title"] == "页面A"
    assert "标题A" in out["cleaned_markdown"]


# ---------------------------------------------------------------- GitHub 连接器(T13.8)


def _github_transport(tree: list[dict], files: dict[str, str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/git/trees/" in url:
            return httpx.Response(200, json={"tree": tree})
        if "/contents/" in url:
            path = url.split("/contents/")[1].split("?")[0]
            body = files.get(path)
            if body is None:
                return httpx.Response(404)
            return httpx.Response(
                200, text=body,
                headers={"content-type": "application/vnd.github.raw"},
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


TREE = [
    {"path": "README.md", "type": "blob", "size": 100},
    {"path": "docs/guide.md", "type": "blob", "size": 100},
    {"path": "docs/api.txt", "type": "blob", "size": 100},
    {"path": "src/main.py", "type": "blob", "size": 100},
    {"path": "docs/design", "type": "tree", "size": 0},
    {"path": "docs/huge.md", "type": "blob", "size": 99 * 1024 * 1024},
]
FILES = {
    "README.md": "# README 内容",
    "docs/guide.md": "# 指南 正文",
    "docs/api.txt": "API 文本",
    "src/main.py": "print('x')",
    "docs/huge.md": "huge",
}


class TestGithubAdapter:
    async def test_fetch_tree_and_filter(self) -> None:
        """trees 枚举 + 前缀/后缀/大小/类型过滤;external_id=路径,url=blob 链接。"""
        from agentplatform.core.kb.connectors.github import fetch as gh_fetch

        result = await gh_fetch(
            {"repo": "acme/docs", "branch": "main", "paths": ["docs"]},
            {"token": "t"},
            transport=_github_transport(TREE, FILES),
        )
        assert result.full is True
        ids = [d.external_id for d in result.docs]
        assert ids == ["docs/guide.md", "docs/api.txt"]
        guide = result.docs[0]
        assert guide.title == "guide.md"
        assert guide.url == "https://github.com/acme/docs/blob/main/docs/guide.md"
        assert "指南" in guide.content_markdown

    async def test_bad_repo_raises(self) -> None:
        from agentplatform.core.kb.connectors.github import fetch as gh_fetch

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        with pytest.raises(ValueError, match="仓库或分支不存在"):
            await gh_fetch({"repo": "acme/nope", "branch": "main"}, {}, transport=httpx.MockTransport(handler))

    async def test_invalid_config_rejected(self) -> None:
        from agentplatform.core.kb.connectors.service import validate_config

        with pytest.raises(KbError, match="owner/repo"):
            validate_config("github", {"repo": "justname"})
        validate_config("github", {"repo": "acme/docs"})  # 合法不抛


# ---------------------------------------------------------------- GitLab 连接器(离职归档)


def _gitlab_transport(tree: list[dict], files: dict[str, str], base: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/repository/tree" in url:
            return httpx.Response(200, json=tree)
        if "/raw" in url:
            path = url.split("/repository/files/")[1].split("/raw")[0]
            from urllib.parse import unquote

            body = files.get(unquote(path))
            if body is None:
                return httpx.Response(404)
            return httpx.Response(200, text=body)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


GITLAB_TREE = [
    {"path": "README.md", "type": "blob", "size": 100},
    {"path": "docs/architecture.md", "type": "blob", "size": 100},
    {"path": "src/main.py", "type": "blob", "size": 100},
    {"path": "docs/pics/logo.png", "type": "blob", "size": 100},
]
GITLAB_FILES = {
    "README.md": "# 内网项目",
    "docs/architecture.md": "# 架构说明",
    "src/main.py": "print()",
}


class TestGitlabAdapter:
    async def test_fetch_filters_and_urls(self) -> None:
        """GitLab v4:树枚举+raw 下载,后缀/路径过滤,URL 指向自托管 blob 页。"""
        from agentplatform.core.kb.connectors.gitlab import fetch as gl_fetch

        result = await gl_fetch(
            {"base_url": "https://gitlab.corp", "repo": "team/project", "branch": "main", "paths": ["docs"]},
            {"token": "glpat-x"},
            transport=_gitlab_transport(GITLAB_TREE, GITLAB_FILES, "https://gitlab.corp"),
        )
        assert result.full is True
        ids = [d.external_id for d in result.docs]
        assert ids == ["docs/architecture.md"]  # README 被前缀过滤;main.py 后缀;png 后缀
        assert result.docs[0].url == "https://gitlab.corp/team/project/-/blob/main/docs/architecture.md"

    async def test_missing_config_raises(self) -> None:
        from agentplatform.core.kb.connectors.gitlab import fetch as gl_fetch

        with pytest.raises(ValueError, match="base_url"):
            await gl_fetch({"repo": "a/b"}, {})

    async def test_validate(self) -> None:
        from agentplatform.core.kb.connectors.service import validate_config

        with pytest.raises(KbError, match="base_url"):
            validate_config("gitlab", {"repo": "a/b"})
        validate_config("gitlab", {"base_url": "https://git.corp", "repo": "group/sub/project"})  # 多级组路径合法
