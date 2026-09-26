"""tool:image_gen —— 文生图(平台内置,M18)。

调用 OpenAI 兼容的 /images/generations 接口(默认走主 LLM 网关,与 chat 同凭据,
零额外配置);产物解码后落盘 ~/.agentplatform/uploads/,经 /api/files/raw 白名单
通道回填 URL——LLM 可直接把 URL 以 <img>/Markdown 嵌入正文,插件(如 writewx
公众号草稿)零凭据复用。与 kb_search/memory/web_search 同款 loop 特判分发。
"""

import base64
import json
import uuid as _uuid
from pathlib import Path

import httpx

from agentplatform.config import settings

IMAGE_GEN_TOOL_ID = "tool:image_gen"

RESOURCE: dict = {
    "id": IMAGE_GEN_TOOL_ID,
    "kind": "tool",
    "name": "image_gen",
    "version": "1.0.0",
    # 实现在本模块(loop 特判 + 通用 executor 双路径可达);缺省会落 builtin 约定路径导致加载失败
    "impl_path": "agentplatform.core.agent.image_gen",
    "description": (
        "根据文字描述生成图片(prompt 越具体效果越好:主体/风格/构图/色调)。"
        "返回图片 URL,可直接以 Markdown 或 <img> 嵌入正文,或用于制作配图/封面。"
    ),
    "schema": {
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "图片描述(中英文均可)"},
                "size": {
                    "type": "string",
                    "description": "尺寸 WxH,默认 1024x1024;横版配图可用 1792x1024",
                },
            },
            "required": ["prompt"],
        },
        "returns": {"type": "string", "description": "图片 URL 列表(JSON)"},
    },
}


def _uploads_dir() -> Path:
    uploads = Path.home() / ".agentplatform" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads


async def run(args: dict) -> str:
    """执行生图;返回 JSON 字符串回填 agent loop。"""
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        return json.dumps({"ok": False, "error": "prompt 不能为空"}, ensure_ascii=False)

    base_url = (settings.image_gen_base_url or settings.openai_base_url).rstrip("/")
    api_key = settings.image_gen_api_key or settings.openai_api_key
    if not base_url or not api_key:
        return json.dumps(
            {
                "ok": False,
                "error": "生图服务未配置:设置 IMAGE_GEN_BASE_URL/IMAGE_GEN_API_KEY,"
                         "或确保主 LLM 网关 OPENAI_BASE_URL/OPENAI_API_KEY 可用",
            },
            ensure_ascii=False,
        )

    size = (args.get("size") or settings.image_gen_size or "").strip() or None
    payload: dict = {"prompt": prompt, "n": 1}
    if settings.image_gen_model:
        payload["model"] = settings.image_gen_model
    if size:
        payload["size"] = size

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{base_url}/images/generations",
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001  回填给 LLM 可自纠
        return json.dumps(
            {"ok": False, "error": f"生图请求失败: {type(exc).__name__}: {exc}"},
            ensure_ascii=False,
        )

    items = data.get("data") or []
    images = []
    for item in items:
        raw = None
        if item.get("b64_json"):
            try:
                raw = base64.b64decode(item["b64_json"])
            except Exception:  # noqa: BLE001  坏数据按失败项跳过
                raw = None
        elif item.get("url"):
            raw = item["url"]
        if not raw:
            continue
        if isinstance(raw, bytes):
            path = _uploads_dir() / f"{_uuid.uuid4().hex}.png"
            path.write_bytes(raw)
            # 签名 URL:HTML 产物 <img>/blob 预览页无法携带 Bearer,签名免头访问;
            # public_api_base 配置时拼绝对地址(blob 页源=WebUI 源,相对 /api 会落到前端 404)
            from agentplatform.api.files import sign_file_path

            url = sign_file_path(str(path))
            if settings.public_api_base:
                url = settings.public_api_base.rstrip("/") + url
        else:
            url = raw
        images.append({"url": url})

    if not images:
        return json.dumps(
            {"ok": False, "error": "生图接口未返回可用图片"}, ensure_ascii=False
        )
    return json.dumps(
        {
            "ok": True,
            "images": images,
            "hint": (
                "在正文中以 Markdown ![描述](url) 或 <img src=\"url\"> 引用;"
                "URL 为平台 /api/files/raw 相对路径,本平台 WebUI 与端侧浏览器均可直接访问。"
            ),
        },
        ensure_ascii=False,
    )
