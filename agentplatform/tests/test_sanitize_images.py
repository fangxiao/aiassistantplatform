"""图片溯源清洗测试(T18.15):编造/失效 <img> 确定性替换占位图。"""

import base64

from agentplatform.core.agent import img_proxy as ip
from agentplatform.core.agent.img_proxy import sanitize_model_images

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class TestSanitizeModelImages:
    def test_fabricated_relative_path_replaced(self) -> None:
        """writewx 实测形态:编造 /images/wx_cover_xxx.png → 占位图 + 警告注释。"""
        out = sanitize_model_images('封面:<img src="/images/wx_cover_8f3a2c.png">')
        assert '<img src="/images/' not in out  # src 已被替换(警告注释回显 URL 属预期)
        assert "data:image/svg+xml" in out
        assert "imgproxy-warnings" in out and "编造形态" in out

    def test_raw_url_existing_file_kept(self, monkeypatch, tmp_path) -> None:
        uploads = tmp_path / ".agentplatform" / "uploads"
        uploads.mkdir(parents=True)
        f = uploads / "real.png"
        f.write_bytes(_PNG_1PX)
        monkeypatch.setattr(ip.Path, "home", staticmethod(lambda: tmp_path))
        html = f'<img src="/api/files/raw?path={f}">'
        assert sanitize_model_images(html) == html  # 真实产物保留

    def test_host_namespace_path_translated(self, monkeypatch, tmp_path) -> None:
        """T18.16:宿主机形态路径(/Users/x/.agentplatform/...)翻译到本服务数据根后按真实文件保留。"""
        uploads = tmp_path / ".agentplatform" / "uploads"
        uploads.mkdir(parents=True)
        f = uploads / "ns.png"
        f.write_bytes(_PNG_1PX)
        monkeypatch.setattr(ip.Path, "home", staticmethod(lambda: tmp_path))
        html = '<img src="/api/files/raw?path=/Users/somebody/.agentplatform/uploads/ns.png">'
        assert sanitize_model_images(html) == html  # 翻译后存在 → 保留

    def test_raw_url_missing_file_replaced(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(ip.Path, "home", staticmethod(lambda: tmp_path))
        out = sanitize_model_images('<img src="/api/files/raw?path=/root/.agentplatform/uploads/ghost.png">')
        assert "data:image/svg+xml" in out and "溯源失败" in out

    def test_proxy_and_data_and_external_kept(self) -> None:
        html = ('<img src="/api/files/img?u=https%3A%2F%2Fx.test%2Fa.png&exp=1&sig=abc">'
                '<img src="data:image/png;base64,AAAA">'
                '<img src="https://cdn.example.com/a.png">')
        assert sanitize_model_images(html) == html  # 代理/内联/外链均保留

    def test_text_without_images_untouched(self) -> None:
        assert sanitize_model_images("纯文本回复") == "纯文本回复"
