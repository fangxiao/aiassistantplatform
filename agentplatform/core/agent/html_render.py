"""tool:html_render —— HTML 渲染公共工具(平台内置,T18.17 sidecar 方案)。

调用渲染 sidecar(独立容器,Playwright+Chromium+python-pptx)把 HTML 转为
PDF/PNG/PPTX;产物落盘 uploads 并返回签名 URL。主 API 镜像不引入渲染引擎
(体积/依赖隔离),sidecar 不可达时优雅降级为可自纠提示。

契约(插件 spec,20260928-1033):入参 {html, formats:["pdf","png","pptx"], scale};
HTML hash 路由约定 #print=打印版、#/N=第 N 页;返回 {pdf_url, png_urls, pptx_url, pages}。
"""

import base64
import json
import uuid as _uuid
from pathlib import Path

import httpx

from agentplatform.config import settings

HTML_RENDER_TOOL_ID = "tool:html_render"

RESOURCE: dict = {
    "id": HTML_RENDER_TOOL_ID,
    "kind": "tool",
    "name": "html_render",
    "version": "1.0.0",
    "impl_path": "agentplatform.core.agent.html_render",
    "description": (
        "把 HTML 渲染为 PDF/PNG/PPTX 文件。HTML 约定:#print 为打印版(整页 PDF),"
        "#/N 为第 N 页(逐页 PNG);返回可直接访问的文件 URL。"
        "适用于文章导出、幻灯片/图文生成等场景。"
    ),
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "html": {"type": "string", "description": "完整 HTML 文档(内联样式/内嵌图片)"},
                "formats": {
                    "type": "array",
                    "description": "输出格式子集:pdf/png/pptx,默认 [\"pdf\"]",
                    "items": {"type": "string", "enum": ["pdf", "png", "pptx"]},
                },
                "scale": {"type": "integer", "description": "PNG 渲染倍率 1-4,默认 2"},
            },
            "required": ["html"],
        },
        "returns": {"type": "string", "description": "渲染产物 URL 列表(JSON)"},
    },
}


def _uploads_dir() -> Path:
    uploads = Path.home() / ".agentplatform" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads


def _signed(path: Path) -> str:
    from agentplatform.api.files import sign_file_path

    url = sign_file_path(str(path))
    base = (settings.public_api_base or "").rstrip("/")
    return base + url if base else url


async def run(args: dict) -> str:
    """执行渲染;返回 JSON 字符串回填 agent loop。"""
    html = (args.get("html") or "").strip()
    if not html:
        return json.dumps({"ok": False, "error": "html 不能为空"}, ensure_ascii=False)

    base = (settings.render_service_url or "http://render:8001").rstrip("/")
    formats = args.get("formats") or ["pdf"]
    payload = {"html": html, "formats": formats, "scale": int(args.get("scale") or 2)}
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(f"{base}/render", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001  回填给 LLM 可自纠
        return json.dumps(
            {"ok": False, "error": f"渲染服务不可用: {type(exc).__name__}: {exc}"}, ensure_ascii=False
        )

    files = data.get("files") or {}
    out: dict = {"ok": True, "pages": data.get("pages", 0)}
    # 契约提示(20260929 sharestudy 反馈):输入缺少 .slide/@page 分页标记时,
    # 渲染服务按单页处理——此处显式告知模型,防止把"只渲染出 1 页"当成符合多页契约
    if out["pages"] <= 1 and ".slide" not in html and "@page" not in html:
        out["warning"] = (
            "输入 HTML 未包含 .slide 或 @page 分页标记,本次按单页渲染;"
            "若任务要求多页 deck,请按契约补齐分页标记后重新渲染"
        )
    up = _uploads_dir()
    if files.get("pdf"):
        p = up / f"{_uuid.uuid4().hex}.pdf"
        p.write_bytes(base64.b64decode(files["pdf"]))
        out["pdf_url"] = _signed(p)
    pngs = files.get("png") or []
    if pngs:
        urls = []
        for b64 in pngs:
            p = up / f"{_uuid.uuid4().hex}.png"
            p.write_bytes(base64.b64decode(b64))
            urls.append(_signed(p))
        out["png_urls"] = urls
    if files.get("pptx"):
        p = up / f"{_uuid.uuid4().hex}.pptx"
        p.write_bytes(base64.b64decode(files["pptx"]))
        out["pptx_url"] = _signed(p)
    if len(out) <= 2:
        return json.dumps({"ok": False, "error": "渲染服务未返回任何产物"}, ensure_ascii=False)
    out["hint"] = "URL 为签名直链(7 天有效),可直接下发 file 控件或嵌入正文。"
    return json.dumps(out, ensure_ascii=False)
