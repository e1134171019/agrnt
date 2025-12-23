"""測試 collector 的資料整併邏輯。"""
import pathlib
import sys
from typing import Dict, Any

import pytest

# 將 ops/ 加入路徑
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "ops"))

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