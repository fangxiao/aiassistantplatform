"""tool:web_search —— 联网搜索(平台内置,M15 P1)。

接 Tavily 协议搜索 API(POST /search,专为 LLM 设计,返回结构化结果);
API key 走 settings(WEB_SEARCH_API_KEY),未配置时优雅降级(返回明确提示,
LLM 会告知用户而非报错崩溃)。与 kb_search/memory 同款 loop 特判分发。
"""

import json

import httpx

from agentplatform.config import settings

WEB_SEARCH_TOOL_ID = "tool:web_search"

RESOURCE: dict = {
    "id": WEB_SEARCH_TOOL_ID,
    "kind": "tool",
    "name": "web_search",
    "version": "1.0.0",
    "description": (
        "联网搜索最新信息。当问题涉及时效性内容(新闻/价格/版本/天气/赛事等)、"
        "知识库与训练数据无法覆盖、或用户明确要求搜索时调用。"
        "引用结果时给出标题与来源 URL。"
    ),
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "max_results": {"type": "integer", "description": "返回条数,默认 5,最大 10"},
            },
            "required": ["query"],
        },
        "returns": {"type": "string", "description": "搜索结果列表(JSON):title/url/content 摘要"},
    },
}


async def run(args: dict) -> str:
    """执行联网搜索;返回 JSON 字符串回填 agent loop。"""
    query = (args.get("query") or "").strip()
    if not query:
        return json.dumps({"ok": False, "error": "query 不能为空"}, ensure_ascii=False)

    provider = settings.web_search_provider.lower()
    max_results = max(1, min(int(args.get("max_results") or 5), 10))
    try:
        if provider == "searxng":
            # 自托管 SearXNG(免费无限;实例需允许 json format)
            if not settings.searxng_base_url:
                return json.dumps(
                    {"ok": False, "error": "SEARXNG_BASE_URL 未配置"}, ensure_ascii=False
                )
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{settings.searxng_base_url.rstrip('/')}/search",
                    params={"q": query, "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()
            results = [
                {"title": r.get("title", ""), "url": r.get("url", ""),
                 "content": (r.get("content") or "")[:500]}
                for r in (data.get("results") or [])[:max_results]
            ]
        else:  # tavily(默认)
            if not settings.web_search_api_key:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "搜索服务未配置:设置 WEB_SEARCH_API_KEY(Tavily)或 "
                                 "切换 WEB_SEARCH_PROVIDER=searxng 使用自托管 SearXNG",
                    },
                    ensure_ascii=False,
                )
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.web_search_api_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "basic",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            results = [
                {"title": r.get("title", ""), "url": r.get("url", ""),
                 "content": (r.get("content") or "")[:500]}
                for r in data.get("results", [])
            ]
    except Exception as exc:  # noqa: BLE001  回填给 LLM 可自纠
        return json.dumps(
            {"ok": False, "error": f"搜索请求失败: {type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "ok": True,
            "query": query,
            "results": results,
            "hint": "引用来源时给出标题与 URL;结果可能与时效相关,重要信息建议交叉验证。",
        },
        ensure_ascii=False,
    )
