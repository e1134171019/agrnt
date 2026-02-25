import pytest
from unittest import mock
from ops import collector
import pathlib

def test_load_config_file_not_found(tmp_path):
    path = tmp_path / "not_exist.yml"
    with pytest.raises(SystemExit):
        collector.load_config(path)

def test_load_config_invalid_yaml(tmp_path):
    path = tmp_path / "bad.yml"
    path.write_text(":::bad_yaml", encoding="utf-8")
    with pytest.raises(SystemExit):
        collector.load_config(path)

def test_load_config_missing_sources(tmp_path):
    path = tmp_path / "no_sources.yml"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        collector.load_config(path)

def test_load_config_missing_required_fields(tmp_path):
    path = tmp_path / "missing_fields.yml"
    path.write_text("""
sources:
  - key: "a"
    name: "b"
    url: "c"
    type: "rss"
    # category 缺失
""", encoding="utf-8")
    with pytest.raises(SystemExit):
        collector.load_config(path)

def test_load_config_invalid_type(tmp_path):
    path = tmp_path / "bad_type.yml"
    path.write_text("""
sources:
  - key: "a"
    name: "b"
    url: "c"
    type: "notype"
    category: "x"
""", encoding="utf-8")
    with pytest.raises(SystemExit):
        collector.load_config(path)

def test_load_config_duplicate_keys(tmp_path):
    path = tmp_path / "dup.yml"
    path.write_text("""
sources:
  - key: "a"
    name: "b"
    url: "c"
    type: "rss"
    category: "x"
  - key: "a"
    name: "c"
    url: "d"
    type: "rss"
    category: "y"
""", encoding="utf-8")
    with pytest.raises(SystemExit):
        collector.load_config(path)

def test_fetch_rss_or_atom_timeout(monkeypatch):
    source = {"name": "test", "url": "http://x", "type": "rss"}
    def timeout(*a, **k): raise collector.requests.Timeout()
    monkeypatch.setattr(collector.requests, "get", timeout)
    result = collector.fetch_rss_or_atom(source)
    assert result == []

def test_fetch_rss_or_atom_http_error(monkeypatch):
    source = {"name": "test", "url": "http://x", "type": "rss"}
    class Resp:
        def raise_for_status(self): raise collector.requests.HTTPError("fail")
    monkeypatch.setattr(collector.requests, "get", lambda *a, **k: Resp())
    result = collector.fetch_rss_or_atom(source)
    assert result == []

def test_fetch_github_discussions_network_error(monkeypatch):
    source = {"name": "test", "url": "http://x", "type": "github_discussions"}
    def bad_get(*a, **k): raise collector.requests.RequestException("fail")
    monkeypatch.setattr(collector.requests, "get", bad_get)
    result = collector.fetch_github_discussions(source)
    assert result == []

def test_fetch_github_discussions_value_error(monkeypatch):
    source = {"name": "test", "url": "http://x", "type": "github_discussions"}
    class Resp:
        def raise_for_status(self): pass
        def json(self): raise ValueError("bad json")
    monkeypatch.setattr(collector.requests, "get", lambda *a, **k: Resp())
    result = collector.fetch_github_discussions(source)
    assert result == []

def test_write_payload_oserror(monkeypatch, tmp_path):
    path = tmp_path / "a.json"
    def bad_write(self, *a, **k): raise OSError("fail")
    monkeypatch.setattr(pathlib.Path, "write_text", bad_write)
    with mock.patch.object(collector.LOGGER, "info"):
        with pytest.raises(OSError):
            collector.write_payload({"a": 1}, path)
