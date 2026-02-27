"""Tests for ops/insight_generator.py"""
import json
import pathlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub out google.genai before importing insight_generator
# (avoids ModuleNotFoundError when google-genai is not installed in dev venv)
# ---------------------------------------------------------------------------
_fake_genai = types.ModuleType("genai")
_fake_genai.Client = MagicMock()  # type: ignore[attr-defined]

_fake_google = types.ModuleType("google")
_fake_google.genai = _fake_genai  # type: ignore[attr-defined]

sys.modules.setdefault("google", _fake_google)
sys.modules.setdefault("google.genai", _fake_genai)
# ---------------------------------------------------------------------------

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "ops"))

import insight_generator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_json_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """建立一個合法的 raw JSON 測試資料檔。"""
    entries = [
        {
            "title": f"Paper {i}",
            "url": f"https://example.com/{i}",
            "summary_raw": f"Summary about manufacturing and CAD {i}",
            "source_key": "arxiv_cs_ro",
            "tags": ["robotics", "manufacturing"],
            "manufacturing_applicability_score": 80 - i,
            "sensor_cad_integration_note": f"Relevant to E0{i}",
        }
        for i in range(5)
    ]
    data = {"meta": {"generated_at": "2025-12-25T00:00:00Z"}, "entries": entries}
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    raw_file = out_dir / "raw-2025-12-25.json"
    raw_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return raw_file


@pytest.fixture
def main_md_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """建立一個模擬的 main digest md 檔案。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    md = "# 技術資訊摘要 - 2025-12-25\n\n## 摘要指標\n\nSome content here\n"
    md_file = out_dir / "digest-2025-12-25-main.md"
    md_file.write_text(md, encoding="utf-8")
    return md_file


# ---------------------------------------------------------------------------
# load_research_context
# ---------------------------------------------------------------------------

class TestLoadResearchContext:
    def test_loads_existing_files(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """確認有效文件能被載入。"""
        doc = tmp_path / "test_doc.md"
        doc.write_text("# Test Research Document\n\nSome content.", encoding="utf-8")

        fake_docs = {"Test Doc": doc}
        monkeypatch.setattr(insight_generator, "RESEARCH_DOCS", fake_docs)

        context = insight_generator.load_research_context()
        assert "Test Research Document" in context
        assert "Test Doc" in context

    def test_skips_missing_files(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """缺少的文件會被跳過，不會引發例外。"""
        fake_docs = {"Missing Doc": tmp_path / "does_not_exist.md"}
        monkeypatch.setattr(insight_generator, "RESEARCH_DOCS", fake_docs)

        context = insight_generator.load_research_context()
        assert context == ""

    def test_truncates_large_files(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """超大文件應被截斷到 15000 字元。"""
        large_doc = tmp_path / "large.md"
        large_doc.write_text("X" * 20000, encoding="utf-8")
        monkeypatch.setattr(insight_generator, "RESEARCH_DOCS", {"Big Doc": large_doc})

        context = insight_generator.load_research_context()
        assert "已截取前段" in context
        assert len(context) < 20000


# ---------------------------------------------------------------------------
# load_today_intel
# ---------------------------------------------------------------------------

class TestLoadTodayIntel:
    def test_returns_empty_if_file_missing(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(insight_generator, "OUT_DIR", tmp_path / "out")
        result = insight_generator.load_today_intel("2099-01-01")
        assert result == ""

    def test_returns_formatted_intel(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, raw_json_file: pathlib.Path) -> None:
        monkeypatch.setattr(insight_generator, "OUT_DIR", raw_json_file.parent)
        result = insight_generator.load_today_intel("2025-12-25")

        assert "Paper 0" in result
        assert "arxiv_cs_ro" in result

    def test_sorts_by_score(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, raw_json_file: pathlib.Path) -> None:
        monkeypatch.setattr(insight_generator, "OUT_DIR", raw_json_file.parent)
        result = insight_generator.load_today_intel("2025-12-25")
        lines = result.split("\n")
        # Paper 0 has highest score (80), should appear first
        first_papers = [l for l in lines if "Paper" in l]
        assert first_papers[0].startswith("[1]")
        assert "Paper 0" in first_papers[0]

    def test_limits_to_80_entries(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """確認只取前 80 篇。"""
        entries = [
            {
                "title": f"Paper {i}",
                "url": f"https://example.com/{i}",
                "summary_raw": "Summary",
                "source_key": "test",
                "tags": [],
                "manufacturing_applicability_score": i,
            }
            for i in range(100)
        ]
        data = {"meta": {}, "entries": entries}
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        f = out_dir / "raw-2025-12-26.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(insight_generator, "OUT_DIR", out_dir)

        result = insight_generator.load_today_intel("2025-12-26")
        # Count number of entries in result
        entry_count = result.count("\n[")
        assert entry_count <= 80


# ---------------------------------------------------------------------------
# generate_insights
# ---------------------------------------------------------------------------

class TestGenerateInsights:
    def test_skips_without_api_key(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """沒有 GEMINI_API_KEY 時應該跳過，不拋出例外。"""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        # Should log error and return gracefully
        insight_generator.generate_insights("2025-12-25")

    def test_skips_if_no_raw_json(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """原始資料不存在時應跳過。"""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(insight_generator, "OUT_DIR", tmp_path / "out")
        monkeypatch.setattr(insight_generator, "RESEARCH_DOCS", {})
        insight_generator.generate_insights("2099-01-01")

    def test_inserts_insight_into_main_md(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """確認 Gemini 分析結果被插入到 main.md 的正確位置。"""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(insight_generator, "OUT_DIR", out_dir)

        # 建立 main.md
        md = "# 技術資訊摘要 - 2025-12-25\n\n## 摘要指標\n\nSome content here\n"
        main_md = out_dir / "digest-2025-12-25-main.md"
        main_md.write_text(md, encoding="utf-8")

        # Mock both helper functions so generate_insights can reach Gemini call
        monkeypatch.setattr(insight_generator, "load_research_context", lambda: "Research context")
        monkeypatch.setattr(insight_generator, "load_today_intel", lambda date: "Intel content")

        mock_response = MagicMock()
        mock_response.text = "**今日戰略洞察:** 命中 E01 金屬反光問題。"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("insight_generator.genai.Client", return_value=mock_client):
            insight_generator.generate_insights("2025-12-25")

        updated = main_md.read_text(encoding="utf-8")
        assert "今日戰略洞察" in updated
        assert "AI 研究情報戰略分析" in updated

    def test_creates_standalone_file_if_no_main_md(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """若 -main.md 不存在則寫入獨立的 insights 檔案。"""
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(insight_generator, "OUT_DIR", out_dir)

        monkeypatch.setattr(insight_generator, "load_research_context", lambda: "Research context")
        monkeypatch.setattr(insight_generator, "load_today_intel", lambda date: "Intel content")

        mock_response = MagicMock()
        mock_response.text = "Insights output"

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("insight_generator.genai.Client", return_value=mock_client):
            insight_generator.generate_insights("2025-12-25")

        insights_file = out_dir / "insights-2025-12-25.md"
        assert insights_file.exists()
        assert "Insights output" in insights_file.read_text(encoding="utf-8")

    def test_handles_gemini_api_error(
        self,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
        raw_json_file: pathlib.Path,
    ) -> None:
        """Gemini API 拋出例外時，應安靜地跳過，不讓整個 CI 崩潰。"""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        monkeypatch.setattr(insight_generator, "OUT_DIR", raw_json_file.parent)
        monkeypatch.setattr(insight_generator, "RESEARCH_DOCS", {})

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API rate limit")

        with patch("insight_generator.genai.Client", return_value=mock_client):
            # Should not raise
            insight_generator.generate_insights("2025-12-25")
