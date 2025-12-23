"""測試 digest.py 的配置載入功能。"""
import pathlib
import sys
from typing import Dict, Any

import pytest
import yaml

# 將 ops/ 加入路徑
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "ops"))

from collector import load_config


class TestLoadConfig:
    """測試 load_config 函式。"""

    def test_load_valid_config(self, sample_feeds_yml: pathlib.Path, sample_config: Dict[str, Any]):
        """測試載入有效的設定檔。"""
        config = load_config(sample_feeds_yml)
        
        assert "sources" in config
        assert len(config["sources"]) == 2
        assert config["sources"][0]["name"] == "Test Source 1"
        assert config["sources"][0]["type"] == "rss"
        assert config["sources"][1]["enabled"] is False

    def test_load_config_file_not_found(self, temp_dir: pathlib.Path):
        """測試檔案不存在時應退出。"""
        non_existent = temp_dir / "non_existent.yml"
        
        with pytest.raises(SystemExit) as exc_info:
            load_config(non_existent)
        
        assert exc_info.value.code == 1

    def test_load_config_invalid_yaml(self, temp_dir: pathlib.Path):
        """測試無效的 YAML 格式應退出。"""
        invalid_yml = temp_dir / "invalid.yml"
        invalid_yml.write_text("{ invalid yaml [", encoding="utf-8")
        
        with pytest.raises(SystemExit) as exc_info:
            load_config(invalid_yml)
        
        assert exc_info.value.code == 1

    def test_load_config_missing_sources(self, temp_dir: pathlib.Path):
        """測試缺少 sources 欄位應退出。"""
        missing_sources = temp_dir / "missing.yml"
        missing_sources.write_text(yaml.dump({"other": "data"}), encoding="utf-8")
        
        with pytest.raises(SystemExit) as exc_info:
            load_config(missing_sources)
        
        assert exc_info.value.code == 1

    def test_load_config_missing_required_fields(self, temp_dir: pathlib.Path):
        """測試來源缺少必填欄位應退出。"""
        invalid_config = {
            "sources": [
                {"name": "Test"}  # 缺少 url 和 type
            ]
        }
        invalid_yml = temp_dir / "invalid_fields.yml"
        invalid_yml.write_text(yaml.dump(invalid_config), encoding="utf-8")
        
        with pytest.raises(SystemExit) as exc_info:
            load_config(invalid_yml)
        
        assert exc_info.value.code == 1

    def test_load_config_invalid_type(self, temp_dir: pathlib.Path):
        """測試 type 欄位值不合法應退出。"""
        invalid_config = {
            "sources": [
                {
                    "key": "invalid",
                    "name": "Test",
                    "url": "https://example.com/feed.xml",
                    "type": "invalid_type"  # 應該是 rss 或 atom
                }
            ]
        }
        invalid_yml = temp_dir / "invalid_type.yml"
        invalid_yml.write_text(yaml.dump(invalid_config), encoding="utf-8")
        
        with pytest.raises(SystemExit) as exc_info:
            load_config(invalid_yml)
        
        assert exc_info.value.code == 1

    def test_load_config_with_optional_fields(self, temp_dir: pathlib.Path):
        """測試選填欄位可正常載入。"""
        config_with_optional = {
            "sources": [
                {
                    "key": "with_optional",
                    "name": "Test",
                    "url": "https://example.com/feed.xml",
                    "type": "rss",
                    "tags": ["tag1", "tag2"],
                    "enabled": True,
                }
            ]
        }
        yml_path = temp_dir / "with_optional.yml"
        yml_path.write_text(yaml.dump(config_with_optional), encoding="utf-8")
        
        config = load_config(yml_path)
        
        assert config["sources"][0]["tags"] == ["tag1", "tag2"]
        assert config["sources"][0]["enabled"] is True

    def test_load_config_duplicate_keys(self, temp_dir: pathlib.Path):
        """測試 key 重複時應退出。"""
        dup_config = {
            "sources": [
                {
                    "key": "dup",
                    "name": "Test",
                    "url": "https://example.com/feed.xml",
                    "type": "rss",
                },
                {
                    "key": "dup",
                    "name": "Test 2",
                    "url": "https://example.com/feed2.xml",
                    "type": "atom",
                },
            ]
        }
        yml_path = temp_dir / "dup.yml"
        yml_path.write_text(yaml.dump(dup_config), encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            load_config(yml_path)

        assert exc_info.value.code == 1

    def test_load_config_empty_sources(self, temp_dir: pathlib.Path):
        """測試空的 sources 列表（不應退出）。"""
        empty_config = {"sources": []}
        yml_path = temp_dir / "empty_sources.yml"
        yml_path.write_text(yaml.dump(empty_config), encoding="utf-8")
        
        config = load_config(yml_path)
        
        assert config["sources"] == []
