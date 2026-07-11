from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trend_commerce.video_content import (
    find_video_campaign,
    generate_video_content_pack,
    write_video_content_pack,
)


class VideoContentTest(unittest.TestCase):
    def test_generate_auhikari_pack_contains_required_materials(self) -> None:
        campaign = find_video_campaign("auhikari")
        pack = generate_video_content_pack(campaign, news_context="引っ越しシーズン", angle="固定費削減")

        self.assertIn("auひかり", pack.narration)
        self.assertIn("https://auhikari-net.com", pack.x_post)
        self.assertGreaterEqual(len(pack.hooks), 3)
        self.assertGreaterEqual(len(pack.image_prompts), 5)
        self.assertIn("広告・PRを含みます", pack.caption)

    def test_write_video_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "pack.md"
            write_video_content_pack("auhikari", output, news_context="通信費見直し")
            text = output.read_text(encoding="utf-8")

        self.assertIn("# auひかり 短尺動画素材パック", text)
        self.assertIn("## ナレーション原稿", text)
        self.assertIn("## 画像生成プロンプト", text)


if __name__ == "__main__":
    unittest.main()
