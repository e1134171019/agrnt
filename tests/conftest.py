"""Pytest 配置與共用 fixtures。"""
import pathlib
import tempfile
from typing import Dict, Any, Generator

import pytest
import yaml


@pytest.fixture
def temp_dir() -> Generator[pathlib.Path, None, None]:
    """建立臨時目錄。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield pathlib.Path(tmpdir)


@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """範例設定檔內容。"""
    return {
        "sources": [
            {
                "key": "source_1",
                "name": "Test Source 1",
                "url": "https://example.com/feed1.xml",
                "type": "rss",
                "tags": ["test", "example"],
                "category": "community",
                "enabled": True,
            },
            {
                "key": "source_2",
                "name": "Test Source 2",
                "url": "https://example.com/feed2.xml",
                "type": "atom",
                "tags": ["test"],
                "category": "news",
                "enabled": False,
            },
        ]
    }


@pytest.fixture
def sample_feeds_yml(temp_dir: pathlib.Path, sample_config: Dict[str, Any]) -> pathlib.Path:
    """建立範例 feeds.yml 檔案。"""
    feeds_path = temp_dir / "feeds.yml"
    feeds_path.write_text(yaml.dump(sample_config), encoding="utf-8")
    return feeds_path


@pytest.fixture
def sample_entries() -> list[Dict[str, Any]]:
    """範例 feed entries。"""
    return [
        {
            "title": "Article 1",
            "link": "https://example.com/1",
            "summary": "Summary 1",
            "published": "2025-12-22",
            "source": "Test Source",
            "tags": ["test"],
            "source_key": "source_1",
            "category": "community",
        },
        {
            "title": "Article 2",
            "link": "https://example.com/2",
            "summary": "Summary 2",
            "published": "2025-12-21",
            "source": "Test Source",
            "tags": ["example"],
            "source_key": "source_1",
            "category": "community",
        },
    ]


@pytest.fixture
def sample_payload_entries() -> list[Dict[str, Any]]:
    """標準化後的 JSON entries。"""
    return [
        {
            "source_key": "source_1",
            "source": "Test Source",
            "title": "Article 1",
            "url": "https://example.com/1",
            "summary_raw": "Summary 1",
            "tags": ["test"],
            "category": "community",
            "fetched_at": "2025-12-22T00:00:00+00:00",
            "published_at": "2025-12-22",
        },
        {
            "source_key": "source_1",
            "source": "Test Source",
            "title": "Article 2",
            "url": "https://example.com/2",
            "summary_raw": "Summary 2",
            "tags": ["example"],
            "category": "community",
            "fetched_at": "2025-12-22T00:00:00+00:00",
            "published_at": "2025-12-21",
        },
    ]
