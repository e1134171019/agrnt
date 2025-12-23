"""測試 digest.py 的資料處理功能。"""
import json
import pathlib
import sys
from typing import Dict, Any

import pytest

# 將 ops/ 加入路徑
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "ops"))

from digest import generate_markdown, load_entries


class TestLoadEntries:
    """測試 JSON 讀取行為。"""

    def test_load_entries_success(self, temp_dir: pathlib.Path, sample_payload_entries: list[Dict[str, Any]]):
        path = temp_dir / "raw.json"
        path.write_text(json.dumps(sample_payload_entries, ensure_ascii=False), encoding="utf-8")

        entries = load_entries(path)

        assert len(entries) == 2
        assert entries[0]["title"] == "Article 1"

    def test_load_entries_missing_file(self, temp_dir: pathlib.Path):
        path = temp_dir / "missing.json"

        with pytest.raises(SystemExit) as exc_info:
            load_entries(path)

        assert exc_info.value.code == 1

    def test_load_entries_invalid_json(self, temp_dir: pathlib.Path):
        path = temp_dir / "invalid.json"
        path.write_text("not json", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            load_entries(path)

        assert exc_info.value.code == 1

    def test_load_entries_not_list(self, temp_dir: pathlib.Path):
        path = temp_dir / "invalid.json"
        path.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            load_entries(path)

        assert exc_info.value.code == 1

    def test_load_entries_missing_fields(self, temp_dir: pathlib.Path):
        path = temp_dir / "invalid.json"
        path.write_text(json.dumps([{"title": "Only"}]), encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            load_entries(path)

        assert exc_info.value.code == 1


class TestGenerateMarkdown:
    """測試 generate_markdown 函式。"""

    def test_generate_empty_entries(self):
        """測試空 entries 列表。"""
        markdown = generate_markdown([], "2025-12-22")
        
        assert "# 技術資訊摘要 - 2025-12-22" in markdown
        assert "*本摘要由自動化系統產生於" in markdown

    def test_generate_single_entry(self):
        """測試單一 entry。"""
        entries = [
            {
                "title": "Test Article",
                "url": "https://example.com/test",
                "summary_raw": "This is a test summary.",
                "published_at": "2025-12-22 10:00",
                "source": "Test Source",
                "tags": ["test", "example"],
            }
        ]
        
        markdown = generate_markdown(entries, "2025-12-22")
        
        assert "# 技術資訊摘要 - 2025-12-22" in markdown
        assert "## Test Source" in markdown
        assert "[Test Article](https://example.com/test)" in markdown
        assert "發布於：2025-12-22 10:00" in markdown
        assert "This is a test summary." in markdown
        assert "**來源**：Test Source" in markdown
        assert "**標籤**：#test #example" in markdown
        assert "---" in markdown

    def test_generate_multiple_sources(self, sample_payload_entries: list[Dict[str, Any]]):
        """測試多個來源分組。"""
        entries = sample_payload_entries + [
            {
                "title": "Article 3",
                "url": "https://example.com/3",
                "summary_raw": "Summary 3",
                "published_at": "2025-12-20",
                "source": "Another Source",  # 不同來源
                "tags": [],
            }
        ]
        
        markdown = generate_markdown(entries, "2025-12-22")
        
        # 檢查來源標題存在（Markdown 中可能有其他 ## 符號）
        assert "## Another Source" in markdown
        assert "## Test Source" in markdown
        # 檢查兩個來源的文章都存在
        assert "[Article 1]" in markdown
        assert "[Article 3]" in markdown

    def test_generate_truncates_long_summary(self):
        """測試長摘要會被截斷。"""
        long_summary = "A" * 300  # 超過 200 字
        entries = [
            {
                "title": "Long Summary",
                "url": "https://example.com/long",
                "summary_raw": long_summary,
                "published_at": "2025-12-22",
                "source": "Test",
                "tags": [],
            }
        ]
        
        markdown = generate_markdown(entries, "2025-12-22")
        
        # 摘要應該被截斷至 200 字 + "..."
        assert long_summary[:200] in markdown
        assert long_summary[:200] + "..." in markdown
        assert len(markdown.split(long_summary[:200])[1].split("...")[0]) == 0  # 確認緊接著是 ...

    def test_generate_no_tags(self):
        """測試無標籤的情況。"""
        entries = [
            {
                "title": "No Tags",
                "url": "https://example.com/notags",
                "summary_raw": "Summary",
                "published_at": "2025-12-22",
                "source": "Test",
                "tags": [],
            }
        ]
        
        markdown = generate_markdown(entries, "2025-12-22")
        
        # 不應該有標籤行
        assert "**標籤**：" not in markdown

    def test_generate_sorted_by_source(self):
        """測試來源按字母排序。"""
        entries = [
            {"title": "Z", "url": "https://z.com", "summary_raw": "", "published_at": "", "source": "Z Source", "tags": []},
            {"title": "A", "url": "https://a.com", "summary_raw": "", "published_at": "", "source": "A Source", "tags": []},
            {"title": "M", "url": "https://m.com", "summary_raw": "", "published_at": "", "source": "M Source", "tags": []},
        ]
        
        markdown = generate_markdown(entries, "2025-12-22")
        
        # 來源應該按字母排序
        lines = markdown.split("\n")
        sources = [line for line in lines if line.startswith("## ")]
        
        assert sources == ["## A Source", "## M Source", "## Z Source"]

    def test_generate_includes_timestamp(self):
        """測試包含產生時間戳記。"""
        markdown = generate_markdown([], "2025-12-22")
        
        # 應包含時間戳記前綴
        assert "*本摘要由自動化系統產生於 " in markdown
