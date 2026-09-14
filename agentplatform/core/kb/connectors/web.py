"""网页/站点连接器(设计 009 §5,需求 U4)。

种子 URL + 可选 sitemap,BFS 同 host 抓取,html_cleaner 去噪转 Markdown。
安全边界(需求 U10):仅 http/https;SSRF DNS 级拦截(禁 loopback/private/
link-local 含云元数据 169.254.169.254/reserved/multicast);手动跟随重定向≤5 次
逐跳复查;单页 5MB;robots.txt 默认遵循。

SSRF 判定与 HTTP 抓取分离:判定函数为纯函数(传 ip 列表)便于单测;
抓取用模块级 httpx.AsyncClient(transport 可注入)。
"""

import asyncio
import ipaddress
import json
import logging
import re
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

from agentplatform.config import settings
from agentplatform.core.kb.connectors.base import FetchedDoc, FetchResult, register_adapter

logger = logging.getLogger(__name__)

_MAX_REDIRECTS = 5
_ALLOWED_SCHEMES = {"http", "https"}

_UA_HEADERS = {"User-Agent": settings.connector_user_agent}


def _is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """SSRF 判定:仅放行全球单播地址(纯函数,单测直接喂 ip)。"""
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_global
        and not addr.is_loopback
        and not addr.is_private
        and not addr.is_link_local  # 含云元数据 169.254.169.254
        and not addr.is_multicast
        and not addr.is_reserved
        and not addr.is_unspecified
    )


async def _resolve_host(host: str) -> list[str]:
    """DNS 解析为 IP 列表(模块级函数,测试可替换以跳过真实解析)。"""
    infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    return [info[4][0] for info in infos]


async def _assert_url_safe(client: httpx.AsyncClient, url: str) -> None:
    """协议白名单 + DNS 解析后逐 IP 复查(防 DNS rebinding 仅查一次,内网场景足够)。"""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"不允许的协议: {parsed.scheme or '(空)'}")
    host = parsed.hostname
    if not host:
        raise ValueError(f"URL 缺少主机: {url}")
    for ip in await _resolve_host(host):
        if not _is_public_ip(ip):
            raise ValueError(f"目标解析到受限地址,已拦截: {host}")


class _LinkExtractor(HTMLParser):
    """提取 <a href> 与 <title>(无外部依赖,与 html_cleaner 同风格)。"""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.links.append(v)
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def normalize_url(url: str) -> str:
    """幂等键:去 fragment 与首尾空白(查询串保留,pathname 保留)。"""
    return urldefrag(url.strip())[0]


def _same_host(a: str, b: str) -> bool:
    """同 host 判定(精确匹配,防子域无限扩散;设计 009 §5)。"""
    return urlparse(a).hostname == urlparse(b).hostname


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    tail = path.rsplit("/", 1)[-1] if path else urlparse(url).hostname or "page"
    tail = re.sub(r"\.[a-zA-Z0-9]+$", "", tail)  # 去 .html 后缀
    tail = re.sub(r"[^0-9A-Za-z一-鿿._-]+", "_", tail).strip("._")
    return tail[:80] or "page"


class _RobotsCache:
    """per-host robots.txt 缓存;获取失败(404/超时)视为允许。"""

    def __init__(self, client: httpx.AsyncClient, respect: bool) -> None:
        self._client = client
        self._respect = respect
        self._cache: dict[str, RobotFileParser | None] = {}

    async def allowed(self, url: str) -> bool:
        if not self._respect:
            return True
        parsed = urlparse(url)
        key = f"{parsed.scheme}://{parsed.netloc}"
        if key not in self._cache:
            rp = RobotFileParser()
            try:
                resp = await self._client.get(f"{key}/robots.txt", headers=_UA_HEADERS)
                if resp.status_code == 200 and resp.text.strip():
                    rp.parse(resp.text.splitlines())
                else:
                    rp = None  # 无 robots 或获取失败:允许
            except Exception:  # noqa: BLE001  robots 不可达不阻塞抓取
                rp = None
            self._cache[key] = rp
        rp = self._cache[key]
        return rp is None or rp.can_fetch("*", url)


async def _fetch_markdown(
    client: httpx.AsyncClient, url: str, robots: _RobotsCache
) -> tuple[str, str, list[str]] | None:
    """抓取单页 → (title, markdown, links);非 HTML/超限/robots 禁止返回 None。"""
    from agentplatform.core.registry.builtin.html_cleaner import run as html_cleaner_run

    await _assert_url_safe(client, url)
    if not await robots.allowed(url):
        logger.info("connector: robots 禁止抓取 %s", url)
        return None

    # 手动跟随重定向,逐跳 SSRF 复查(自动跟随无法拦截跳向内网的目标)
    target = url
    for hop in range(_MAX_REDIRECTS + 1):
        resp = await client.get(target, headers=_UA_HEADERS)
        if resp.status_code // 100 == 3 and "location" in resp.headers:
            if hop == _MAX_REDIRECTS:
                return None
            target = normalize_url(urljoin(target, resp.headers["location"]))
            continue
        break
    else:  # pragma: no cover - for 循环正常 break 不会走到
        return None
    if resp.status_code != 200:
        return None
    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return None
    if len(resp.content) > settings.connector_max_page_bytes:
        logger.info("connector: 页面超过大小上限,跳过 %s", url)
        return None
    html = resp.text

    result = json.loads(html_cleaner_run(html, extract_tables=False))
    links: list[str] = []
    extractor = _LinkExtractor()
    extractor.feed(html)
    base = str(resp.url)
    for href in extractor.links:
        absolute = normalize_url(urljoin(base, href))
        if urlparse(absolute).scheme in _ALLOWED_SCHEMES:
            links.append(absolute)
    return result.get("title") or "", result.get("cleaned_markdown") or "", links


async def _sitemap_urls(client: httpx.AsyncClient, sitemap: str, seeds: list[str]) -> list[str]:
    """展开 sitemap.xml(单层 <loc>;支持 <sitemapindex> 一层嵌套)。"""
    import xml.etree.ElementTree as ET

    urls: list[str] = list(seeds)
    try:
        resp = await client.get(sitemap, headers=_UA_HEADERS)
        if resp.status_code != 200:
            return urls
        root = ET.fromstring(resp.content)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        if root.tag.endswith("sitemapindex"):
            for sm in root.findall("s:sitemap/s:loc", ns):
                urls.extend(await _sitemap_urls(client, sm.text.strip(), []))
        else:
            for loc in root.findall("s:url/s:loc", ns) or root.findall(".//{*}loc"):
                if loc.text:
                    urls.append(loc.text.strip())
    except Exception as exc:  # noqa: BLE001  sitemap 失败不阻断种子抓取
        logger.warning("connector: sitemap 解析失败 %s: %s", sitemap, exc)
    return urls


async def fetch(
    config: dict,
    credentials: dict,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FetchResult:
    """网页数据源抓取:种子 + sitemap BFS 同 host,产出 Markdown 文档(全量型)。"""
    seeds = [normalize_url(u) for u in (config.get("urls") or []) if str(u).strip()]
    if not seeds:
        raise ValueError("未配置种子 URL(config.urls)")
    max_depth = max(0, int(config.get("max_depth", 2)))
    hard_cap = settings.connector_max_pages
    max_pages = min(int(config.get("max_pages", hard_cap)), hard_cap)
    respect_robots = bool(config.get("respect_robots", True))

    async with httpx.AsyncClient(
        transport=transport,
        timeout=settings.connector_fetch_timeout_s,
        follow_redirects=False,
    ) as client:
        robots = _RobotsCache(client, respect_robots)
        seeds_expanded = list(seeds)
        if config.get("sitemap"):
            seeds_expanded = await _sitemap_urls(client, str(config["sitemap"]), seeds)
        queue: list[tuple[str, int]] = []
        seen: set[str] = set()
        for u in seeds_expanded:
            u = normalize_url(u)
            if u not in seen:
                seen.add(u)
                queue.append((u, 0))

        docs: list[FetchedDoc] = []
        while queue and len(docs) < max_pages:
            url, depth = queue.pop(0)
            try:
                page = await _fetch_markdown(client, url, robots)
            except Exception as exc:  # noqa: BLE001  单页失败不中断整次同步(验收 8)
                logger.warning("connector: 抓取失败 %s: %s", url, exc)
                continue
            if page is None:
                continue
            title, markdown, links = page
            if markdown.strip():
                docs.append(
                    FetchedDoc(
                        external_id=url,
                        url=url,
                        title=title.strip() or _slug_from_url(url),
                        content_markdown=markdown,
                    )
                )
            if depth < max_depth:
                for link in links:
                    if (
                        link not in seen
                        and len(seen) < max_pages * 4  # 候选队列也限量,防大站撑爆内存
                        and _same_host(link, seeds[0])
                    ):
                        seen.add(link)
                        queue.append((link, depth + 1))

    return FetchResult(docs=docs, full=True)


register_adapter("web", fetch)
