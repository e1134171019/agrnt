"""測試 digest.py 的資料處理功能。"""
import pathlib
import sys
from typing import Dict, Any

import pytest

# 將 ops/ 加入路徑
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "ops"))

from digest import merge_entries, generate_markdown


class TestMergeEntries:
    """測試 merge_entries 函式。"""

    def test_merge_empty_lists(self):
        """測試合併空列表。"""
        result = merge_entries([])
        assert result == []

    def test_merge_single_source(self, sample_entries: list[Dict[str, Any]]):
        """測試合併單一來源。"""
        result = merge_entries([sample_entries])
        
        assert len(result) == 2
        assert result[0]["title"] == "Article 1"
        assert result[1]["title"] == "Article 2"

    def test_merge_multiple_sources(self, sample_entries: list[Dict[str, Any]]):
        """測試合併多個來源。"""
        source2 = [
            {
                "title": "Article 3",
                "link": "https://example.com/3",
                "summary": "Summary 3",
                "published": "2025-12-20",
                "source": "Another Source",
                "tags": ["other"],
            }
        ]
        
        result = merge_entries([sample_entries, source2])
        
        assert len(result) == 3
        assert result[2]["source"] == "Another Source"

    def test_merge_removes_duplicates(self):
        """測試去重功能（依 link）。"""
        entries1 = [
            {
                "title": "Article 1",
                "link": "https://example.com/same",
                "summary": "Summary 1",
                "published": "2025-12-22",
                "source": "Source 1",
                "tags": [],
            }
        ]
        entries2 = [
            {
                "title": "Article 1 Duplicate",  # 標題不同但 link 相同
                "link": "https://example.com/same",
                "summary": "Summary 2",
                "published": "2025-12-21",
                "source": "Source 2",
                "tags": [],
            }
        ]
        
        result = merge_entries([entries1, entries2])
        
        # 應該只保留第一個
        assert len(result) == 1
        assert result[0]["title"] == "Article 1"
        assert result[0]["source"] == "Source 1"

    def test_merge_preserves_order(self):
        """測試保留順序（先來先得）。"""
        entries1 = [
            {"title": "A", "link": "https://a.com", "summary": "", "published": "", "source": "S1", "tags": []},
            {"title": "B", "link": "https://b.com", "summary": "", "published": "", "source": "S1", "tags": []},
        ]
        entries2 = [
            {"title": "C", "link": "https://c.com", "summary": "", "published": "", "source": "S2", "tags": []},
        ]
        
        result = merge_entries([entries1, entries2])
        
        assert len(result) == 3
        assert result[0]["title"] == "A"
        assert result[1]["title"] == "B"
        assert result[2]["title"] == "C"

    def test_merge_empty_link_not_filtered(self):
        """測試空 link 的 entry 會被跳過。"""
        entries = [
            {"title": "No Link", "link": "", "summary": "", "published": "", "source": "S1", "tags": []},
            {"title": "Has Link", "link": "https://example.com", "summary": "", "published": "", "source": "S1", "tags": []},
        ]
        
        result = merge_entries([entries])
        
        # 空 link 被過濾
        assert len(result) == 1
        assert result[0]["title"] == "Has Link"


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
                "link": "https://example.com/test",
                "summary": "This is a test summary.",
                "published": "2025-12-22 10:00",
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

    def test_generate_multiple_sources(self, sample_entries: list[Dict[str, Any]]):
        """測試多個來源分組。"""
        entries = sample_entries + [
            {
                "title": "Article 3",
                "link": "https://example.com/3",
                "summary": "Summary 3",
                "published": "2025-12-20",
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
                "link": "https://example.com/long",
                "summary": long_summary,
                "published": "2025-12-22",
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
                "link": "https://example.com/notags",
                "summary": "Summary",
                "published": "2025-12-22",
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
            {"title": "Z", "link": "https://z.com", "summary": "", "published": "", "source": "Z Source", "tags": []},
            {"title": "A", "link": "https://a.com", "summary": "", "published": "", "source": "A Source", "tags": []},
            {"title": "M", "link": "https://m.com", "summary": "", "published": "", "source": "M Source", "tags": []},
        ]
        
        markdown = generate_markdown(entries, "2025-12-22")
        
        # 來源應該按字母排序
        lines = markdown.split("\n")
        sources = [line for line in lines if line.startswith("## ")]
        
        assert sources == ["## A Source", "## M Source", "## Z Source"]

    def test_generate_includes_timestamp(self):
        """測試包含產生時間戳記。"""
        markdown = generate_markdown([], "2025-12-22")
        
        # 時間戳記應該是當前時間
        assert "*本摘要由自動化系統產生於 2025-12-22" in markdown
