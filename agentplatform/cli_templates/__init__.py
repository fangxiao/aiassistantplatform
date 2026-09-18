"""插件模板库(M16,设计 013):平台下发、CLI init --template 消费。

准入规则:每个模板的骨架必须 validate 零错误、test 全过(单测覆盖)——
模板质量即生态门面。plugin.yaml 中 {plugin_name} 占位符由 init 替换。
"""

from pathlib import Path

TEMPLATES: dict[str, dict] = {}

_MODULE_DIR = Path(__file__).parent


def _load(template_id: str) -> dict:
    """从目录加载模板:{id: {name, description, files{相对路径: 内容}}}。"""
    base = _MODULE_DIR / template_id
    meta_path = base / "template.yaml"
    import yaml

    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    files: dict[str, str] = {}
    for f in sorted(base.rglob("*")):
        if f.is_file() and f.name != "template.yaml":
            rel = f.relative_to(base).as_posix()
            files[rel] = f.read_text(encoding="utf-8")
    return {
        "id": template_id,
        "name": meta["name"],
        "description": meta["description"],
        "files": files,
    }


for _tid in ("starter", "weekly-report", "doc-summarizer", "web-digest"):
    try:
        TEMPLATES[_tid] = _load(_tid)
    except FileNotFoundError:
        continue
