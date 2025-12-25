"""測試 collector 的資料整併與抓取邏輯。"""
import datetime as dt
import json
import pathlib
import sys
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest
import requests

# 將 ops/ 加入路徑
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "ops"))

import collector
from collector import build_payload, merge_entries


def test_merge_empty_lists():
    assert merge_entries([]) == []


def test_merge_deduplicates(sample_entries: list[Dict[str, Any]]):
    dup = sample_entries + [
        {
            "title": "Dup",
            "link": sample_entries[0]["link"],
            "summary": "Summary",
            "published": "2025-12-23",
            "source": "Another",
            "tags": [],
            "source_key": "source_2",
        }
    ]

    merged = merge_entries([dup])

    assert len(merged) == 2
    assert merged[0]["title"] == "Article 1"


def test_merge_preserves_order(sample_entries: list[Dict[str, Any]]):
    merged = merge_entries([sample_entries])
    titles = [item["title"] for item in merged]
    assert titles == ["Article 1", "Article 2"]


def test_build_payload_structure(sample_entries: list[Dict[str, Any]]):
    payload = build_payload(sample_entries)

    assert len(payload) == 2
    entry = payload[0]
    assert entry["source_key"] == "source_1"
    assert entry["summary_raw"] == "Summary 1"
    assert entry["url"] == "https://example.com/1"
    assert entry["category"] == "community"
    assert "fetched_at" in entry
    assert entry["published_at"] == "2025-12-22"


def test_build_payload_handles_missing_fields():
    raw_entries = [
        {
            "title": "Missing",
            "link": "",
            "summary": "",
            "published": "",
            "source": "Test",
            "source_key": "key",
            "tags": [],
        }
    ]

    payload = build_payload(raw_entries)

    assert payload[0]["url"] == ""
    assert payload[0]["source"] == "Test"
    assert payload[0]["category"] == "未分類"


class DummyResponse:
    """簡化版 HTTP 回應物件。"""

    def __init__(self, *, content: bytes = b"", json_data: Dict[str, Any] | None = None) -> None:
        self.content = content
        self._json = json_data or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Dict[str, Any]:
        return self._json


class TestFetchRssOrAtom:
    """測試 RSS/Atom 抓取流程。"""

    def test_fetch_rss_or_atom_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source = {
            "name": "Sample Feed",
            "url": "https://example.com/rss",
            "limit": 1,
            "tags": ["tag"],
            "key": "sample",
            "category": "community",
        }
        fake_response = DummyResponse(content=b"<rss>")

        def fake_get(url: str, timeout: int) -> DummyResponse:
            assert url == source["url"]
            assert timeout == collector.REQUEST_TIMEOUT
            return fake_response

        def fake_parse(content: bytes) -> SimpleNamespace:
            assert content == fake_response.content
            entries = [
                {
                    "title": "Entry",
                    "link": "https://example.com/entry",
                    "summary": "Summary",
                    "published": "2025-12-25",
                }
            ]
            return SimpleNamespace(entries=entries, bozo=False)

        monkeypatch.setattr(collector.requests, "get", fake_get)
        monkeypatch.setattr(collector.feedparser, "parse", fake_parse)

        entries = collector.fetch_rss_or_atom(source)

        assert len(entries) == 1
        assert entries[0]["title"] == "Entry"
        assert entries[0]["source"] == "Sample Feed"
        assert entries[0]["category"] == "community"

    def test_fetch_rss_or_atom_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source = {"name": "Timeout Feed", "url": "https://example.com/rss"}
        attempts: List[int] = []

        def fake_get(url: str, timeout: int) -> None:
            attempts.append(1)
            raise requests.Timeout("boom")

        monkeypatch.setattr(collector.requests, "get", fake_get)
        monkeypatch.setattr(collector.time, "sleep", lambda *_: None)

        entries = collector.fetch_rss_or_atom(source)

        assert entries == []
        assert len(attempts) == collector.MAX_RETRIES


class TestFetchProductHunt:
    """測試 Product Hunt GraphQL 抓取流程。"""

    def test_fetch_producthunt_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source = {
            "name": "Product Hunt Daily",
            "key": "producthunt_daily",
            "tags": ["startup"],
            "limit": 2,
            "category": "product",
        }

        def fake_getenv(key: str) -> str:
            assert key == collector.PRODUCTHUNT_TOKEN_ENV
            return "token"

        response_payload = {
            "data": {
                "posts": {
                    "edges": [
                        {
                            "node": {
                                "name": "Tool",
                                "tagline": "Tagline",
                                "description": "Description",
                                "website": "https://producthunt.com/tool",
                                "url": "https://producthunt.com/posts/tool",
                                "createdAt": "2025-12-25",
                                "topics": {
                                    "edges": [
                                        {"node": {"name": "AI"}},
                                        {"node": {"name": "startup"}},
                                    ]
                                },
                            }
                        }
                    ]
                }
            }
        }

        def fake_post(url: str, json: Dict[str, Any], headers: Dict[str, Any], timeout: int) -> DummyResponse:
            assert url == collector.PRODUCTHUNT_API_URL
            assert json["variables"]["first"] == source["limit"]
            assert headers["Authorization"] == "Bearer token"
            return DummyResponse(json_data=response_payload)

        monkeypatch.setattr(collector.os, "getenv", fake_getenv)
        monkeypatch.setattr(collector.requests, "post", fake_post)

        entries = collector.fetch_producthunt(source)

        assert len(entries) == 1
        entry = entries[0]
        assert entry["title"] == "Tool"
        assert entry["link"] == "https://producthunt.com/tool"
        # tags 應包含來源 tags 與 topics，且去重後仍保留原始順序
        assert entry["tags"] == ["startup", "AI"]
        assert entry["category"] == "product"

    def test_fetch_producthunt_missing_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        source = {"name": "PH", "key": "producthunt_daily"}
        monkeypatch.setattr(collector.os, "getenv", lambda _key: None)

        entries = collector.fetch_producthunt(source)

        assert entries == []


class TestFetchSource:
    """測試 fetch_source 的派發邏輯。"""

    def test_fetch_source_dispatch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        rss_source = {"type": "rss"}
        ph_source = {"type": "producthunt"}

        monkeypatch.setattr(collector, "fetch_rss_or_atom", lambda src: [src])
        monkeypatch.setattr(collector, "fetch_producthunt", lambda src: [src])

        assert collector.fetch_source(rss_source) == [rss_source]
        assert collector.fetch_source(ph_source) == [ph_source]


class TestSetupLogging:
    """測試 setup_logging 的 handler 組態。"""

    def test_setup_logging_configures_handlers(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded: Dict[str, Any] = {}

        def fake_basic_config(**kwargs: Any) -> None:  # type: ignore[override]
            recorded["kwargs"] = kwargs

        monkeypatch.setattr(collector.logging, "basicConfig", fake_basic_config)
        log_file = tmp_path / "collector.log"

        collector.setup_logging(verbose=True, log_file=log_file)

        assert log_file.exists()
        assert "kwargs" in recorded
        handlers = recorded["kwargs"].get("handlers", [])
        assert len(handlers) == 2
        assert recorded["kwargs"].get("level") == collector.logging.DEBUG


def test_write_payload_writes_json(
    tmp_path: pathlib.Path, sample_payload_entries: list[Dict[str, Any]]
) -> None:
    output = tmp_path / "raw-2025-12-25.json"

    document = {"meta": {"foo": "bar"}, "entries": sample_payload_entries}
    collector.write_payload(document, output)

    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["meta"] == {"foo": "bar"}
    assert data["entries"][0]["title"] == "Article 1"
    assert data["entries"][1]["source"] == "Test Source"


class TestParseArgsCollector:
    """測試 collector.parse_args 行為。"""

    def test_parse_args_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["collector.py"])

        args = collector.parse_args()

        assert args.date == dt.date.today().isoformat()
        assert args.output is None
        assert args.dry_run is False
        assert args.verbose is False

    def test_parse_args_overrides(self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
        output_path = tmp_path / "custom.json"
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "collector.py",
                "--date",
                "2025-12-30",
                "--output",
                str(output_path),
                "--dry-run",
                "--verbose",
            ],
        )

        args = collector.parse_args()

        assert args.date == "2025-12-30"
        assert args.output == output_path
        assert args.dry_run is True
        assert args.verbose is True


class TestMain:
    """測試 collector.main 的互動流程。"""

    def test_main_dry_run_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sample_entries: list[Dict[str, Any]],
    ) -> None:
        fake_args = SimpleNamespace(date="2025-12-30", output=None, dry_run=True, verbose=False)
        monkeypatch.setattr(collector, "parse_args", lambda: fake_args)

        monkeypatch.setattr(collector, "setup_logging", lambda **_: None)
        monkeypatch.setattr(
            collector,
            "load_config",
            lambda _path: {"sources": [{"key": "source_1", "type": "rss", "enabled": True}]},
        )
        monkeypatch.setattr(collector, "fetch_source", lambda _src: sample_entries)

        collector.main()

    def test_main_writes_payload(
        self,
        monkeypatch: pytest.MonkeyPatch,
        sample_entries: list[Dict[str, Any]],
        tmp_path: pathlib.Path,
    ) -> None:
        output_path = tmp_path / "raw.json"
        fake_args = SimpleNamespace(date="2025-12-30", output=output_path, dry_run=False, verbose=True)
        monkeypatch.setattr(collector, "parse_args", lambda: fake_args)
        monkeypatch.setattr(collector, "setup_logging", lambda **_: None)
        monkeypatch.setattr(
            collector,
            "load_config",
            lambda _path: {"sources": [{"key": "source_1", "type": "rss", "enabled": True}]},
        )
        monkeypatch.setattr(collector, "fetch_source", lambda _src: sample_entries)

        recorded: Dict[str, Any] = {}

        def fake_write_payload(document: Dict[str, Any], path: pathlib.Path) -> None:
            recorded["count"] = len(document["entries"])
            recorded["path"] = path
            recorded["meta"] = document["meta"]

        monkeypatch.setattr(collector, "write_payload", fake_write_payload)

        collector.main()

        assert recorded["count"] == len(sample_entries)
        assert recorded["path"] == output_path
        assert recorded["meta"]["raw_entries"] == len(sample_entries)
        assert recorded["meta"]["failed_source_count"] == 0

    def test_main_exits_when_no_sources(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_args = SimpleNamespace(date="2025-12-30", output=None, dry_run=False, verbose=False)
        monkeypatch.setattr(collector, "parse_args", lambda: fake_args)
        monkeypatch.setattr(collector, "setup_logging", lambda **_: None)
        monkeypatch.setattr(collector, "load_config", lambda _path: {"sources": []})

        with pytest.raises(SystemExit) as exc_info:
            collector.main()

        assert exc_info.value.code == 2

    def test_main_exits_when_all_sources_fail(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_args = SimpleNamespace(date="2025-12-30", output=None, dry_run=False, verbose=False)
        monkeypatch.setattr(collector, "parse_args", lambda: fake_args)
        monkeypatch.setattr(collector, "setup_logging", lambda **_: None)
        monkeypatch.setattr(
            collector,
            "load_config",
            lambda _path: {"sources": [{"key": "source_1", "type": "rss", "enabled": True}]},
        )
        monkeypatch.setattr(collector, "fetch_source", lambda _src: [])

        with pytest.raises(SystemExit) as exc_info:
            collector.main()

        assert exc_info.value.code == 2

    def test_main_write_payload_error(self, monkeypatch: pytest.MonkeyPatch, sample_entries: list[Dict[str, Any]]) -> None:
        fake_args = SimpleNamespace(date="2025-12-30", output=None, dry_run=False, verbose=False)
        monkeypatch.setattr(collector, "parse_args", lambda: fake_args)
        monkeypatch.setattr(collector, "setup_logging", lambda **_: None)
        monkeypatch.setattr(
            collector,
            "load_config",
            lambda _path: {"sources": [{"key": "source_1", "type": "rss", "enabled": True}]},
        )
        monkeypatch.setattr(collector, "fetch_source", lambda _src: sample_entries)

        def fake_write_payload(_payload: List[Dict[str, Any]], _path: pathlib.Path) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(collector, "write_payload", fake_write_payload)

        with pytest.raises(SystemExit) as exc_info:
            collector.main()

        assert exc_info.value.code == 3