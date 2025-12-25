"""測試 digest.py 的資料處理功能。"""
import datetime as dt
import json
import logging
import pathlib
import sys
from types import SimpleNamespace
from typing import Dict, Any

import pytest

# 將 ops/ 加入路徑
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "ops"))

import digest
from digest import LOGGER, generate_markdown, load_entries, parse_args, setup_logging


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


class TestParseArgs:
    """測試 parse_args() 的 argparse 行為。"""

    class _FakeDate(dt.date):
        @classmethod
        def today(cls) -> dt.date:  # type: ignore[override]
            return cls(2025, 12, 25)

    def test_parse_args_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(digest.dt, "date", self._FakeDate)
        monkeypatch.setattr(sys, "argv", ["prog"])

        args = parse_args()

        assert args.date == "2025-12-25"
        assert args.input is None
        assert args.output is None
        assert args.dry_run is False
        assert args.verbose is False

    def test_parse_args_overrides(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
        input_path = tmp_path / "custom.json"
        output_path = tmp_path / "digest.md"
        argv = [
            "prog",
            "--date",
            "2024-01-02",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--dry-run",
            "--verbose",
        ]
        monkeypatch.setattr(sys, "argv", argv)

        args = parse_args()

        assert args.date == "2024-01-02"
        assert args.input == input_path
        assert args.output == output_path
        assert args.dry_run is True
        assert args.verbose is True

    def test_parse_args_invalid_argument(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["prog", "--unknown"])

        with pytest.raises(SystemExit):
            parse_args()


class TestSetupLogging:
    """測試 setup_logging() 的 handler 與輸出。"""

    def test_setup_logging_creates_handlers(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # 確保 logging.basicConfig 可重新安裝 handler
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        log_file = tmp_path / "digest.log"

        setup_logging(verbose=True, log_file=log_file)
        LOGGER.debug("debug message")
        LOGGER.info("file message")
        captured = capsys.readouterr()

        assert LOGGER.isEnabledFor(logging.DEBUG)
        assert "debug message" in captured.out
        assert log_file.exists()
        assert "file message" in log_file.read_text(encoding="utf-8")

        # 測試結束後清理 handler，避免影響其他測試
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()

class TestMainFlow:
    """測試 main() 流程控制。"""

    def test_main_generates_markdown(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        out_dir = tmp_path / "out"
        logs_dir = tmp_path / "logs"
        monkeypatch.setattr(digest, "OUT_DIR", out_dir)
        monkeypatch.setattr(digest, "LOGS_DIR", logs_dir)

        args = SimpleNamespace(
            date="2025-12-25",
            input=None,
            output=None,
            dry_run=False,
            verbose=False,
        )
        monkeypatch.setattr(digest, "parse_args", lambda: args)

        entries = [
            {
                "title": "Main Entry",
                "url": "https://example.com",
                "summary_raw": "Summary",
                "published_at": "2025-12-25",
                "source": "Main Source",
                "tags": [],
            }
        ]
        monkeypatch.setattr(digest, "load_entries", lambda path: entries)
        monkeypatch.setattr(digest, "generate_markdown", lambda _entries, _date: "MARKDOWN")

        digest.main()

        output_path = out_dir / "digest-2025-12-25.md"
        assert output_path.exists()
        assert output_path.read_text(encoding="utf-8") == "MARKDOWN"
        log_path = logs_dir / "digest-2025-12-25.log"
        assert log_path.exists()

    def test_main_dry_run_prints_markdown(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(digest, "OUT_DIR", tmp_path)
        monkeypatch.setattr(digest, "LOGS_DIR", tmp_path / "logs")

        args = SimpleNamespace(
            date="2025-12-24",
            input=tmp_path / "raw.json",
            output=None,
            dry_run=True,
            verbose=True,
        )
        monkeypatch.setattr(digest, "parse_args", lambda: args)

        entries = [
            {
                "title": "Dry Entry",
                "url": "https://dry.run",
                "summary_raw": "Dry summary",
                "published_at": "2025-12-24",
                "source": "Dry Source",
                "tags": [],
            }
        ]
        monkeypatch.setattr(digest, "load_entries", lambda path: entries)
        monkeypatch.setattr(digest, "generate_markdown", lambda *_: "DRY")

        digest.main()

        captured = capsys.readouterr()
        assert "DRY" in captured.out
        output_path = tmp_path / "digest-2025-12-24.md"
        assert not output_path.exists()

    def test_main_exits_when_no_entries(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: pathlib.Path,
    ) -> None:
        monkeypatch.setattr(digest, "OUT_DIR", tmp_path)
        monkeypatch.setattr(digest, "LOGS_DIR", tmp_path / "logs")

        args = SimpleNamespace(
            date="2025-12-23",
            input=None,
            output=None,
            dry_run=False,
            verbose=False,
        )
        monkeypatch.setattr(digest, "parse_args", lambda: args)
        monkeypatch.setattr(digest, "load_entries", lambda path: [])

        with pytest.raises(SystemExit) as exc_info:
            digest.main()

        assert exc_info.value.code == 2
