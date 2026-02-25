import pytest
from unittest.mock import patch, MagicMock
import ops.web_crawler as web_crawler

@pytest.fixture
def sample_source():
    return {
        "name": "測試來源",
        "key": "test",
        "url": "http://example.com",
        "selector": "div.item",
        "fields": {
            "title": "h2.title",
            "url": "a::attr(href)",
            "summary": "p.desc"
        },
        "limit": 2,
        "category": "測試分類",
        "tags": ["tag1", "tag2"]
    }

@pytest.fixture
def sample_html():
    return '''
    <html><body>
      <div class="item">
        <h2 class="title">標題1</h2>
        <a href="/link1">連結</a>
        <p class="desc">摘要1</p>
      </div>
      <div class="item">
        <h2 class="title">標題2</h2>
        <a href="/link2">連結</a>
        <p class="desc">摘要2</p>
      </div>
    </body></html>
    '''

# 1. fetch_web_source 正常抓到資料
@patch("ops.web_crawler.requests.get")
def test_fetch_web_source_success(mock_get, sample_source, sample_html):
    mock_resp = MagicMock()
    mock_resp.text = sample_html
    mock_resp.raise_for_status = lambda: None
    mock_get.return_value = mock_resp
    result = web_crawler.fetch_web_source(sample_source)
    assert len(result) == 2
    assert result[0]["title"] == "標題1"
    assert result[0]["link"].endswith("/link1")
    assert result[0]["summary"] == "摘要1"
    assert result[1]["title"] == "標題2"

# 2. fetch_web_source 超時時回傳空列表
@patch("ops.web_crawler.requests.get", side_effect=web_crawler.requests.exceptions.Timeout)
def test_fetch_web_source_timeout(mock_get, sample_source):
    result = web_crawler.fetch_web_source(sample_source)
    assert result == []

# 3. fetch_web_source HTTP 錯誤時回傳空列表
@patch("ops.web_crawler.requests.get")
def test_fetch_web_source_http_error(mock_get, sample_source):
    mock_resp = MagicMock()
    def raise_http():
        raise web_crawler.requests.exceptions.HTTPError("404")
    mock_resp.raise_for_status = raise_http
    mock_get.return_value = mock_resp
    result = web_crawler.fetch_web_source(sample_source)
    assert result == []

# 4. _parse_with_fields 正確解析 HTML
def test_parse_with_fields_success():
    from bs4 import BeautifulSoup
    from ops.web_crawler import _parse_with_fields

    html = """
    <div class="item">
        <h2><a href="/article/1">測試標題</a></h2>
        <p>測試摘要內容</p>
    </div>
    <div class="item">
        <h2><a href="/article/2">第二篇</a></h2>
        <p>第二篇摘要</p>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    source = {
        "name": "測試來源",
        "key": "test",
        "url": "https://example.com",
        "selector": "div.item",
        "fields": {
            "title": "h2 a",
            "url": "h2 a::attr(href)",
            "summary": "p",
        },
        "limit": 10,
        "tags": [],
        "category": "test",
    }
    result = _parse_with_fields(soup, source)
    assert len(result) == 2
    assert result[0]["title"] == "測試標題"
    assert result[1]["title"] == "第二篇"

# 5. _parse_with_fields selector 找不到時回傳空列表
@patch("ops.web_crawler.BeautifulSoup")
def test_parse_with_fields_no_items(mock_bs, sample_source):
    soup = web_crawler.BeautifulSoup("<html></html>", "html.parser")
    result = web_crawler._parse_with_fields(soup, sample_source)
    assert result == []

# 6. bs4 未安裝時（_BS4_AVAILABLE = False）回傳空列表
@patch("ops.web_crawler._BS4_AVAILABLE", False)
def test_fetch_web_source_bs4_missing(sample_source):
    result = web_crawler.fetch_web_source(sample_source)
    assert result == []
