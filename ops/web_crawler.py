"""網頁爬蟲模組：抓取 type: web 來源，相容 feeds.yml fields 設計。"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

try:
    import requests
except ImportError as exc:
    raise SystemExit("請先安裝 requests：pip install requests") from exc

try:
    from bs4 import BeautifulSoup  # type: ignore
except ImportError as exc:
    raise SystemExit("請先安裝 beautifulsoup4：pip install beautifulsoup4") from exc

LOGGER = logging.getLogger("web_crawler")

REQUEST_TIMEOUT = 10
MAX_RETRIES = 2
RETRY_DELAY = 2

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


def _resolve_field(item: Any, selector_str: Optional[str], base_url: str = "") -> str:
    """
    解析單一欄位。支援兩種語法：
      - "h2 a"              → 取文字內容
      - "h2 a::attr(href)" → 取屬性值
    """
    if not selector_str:
        return ""

    if "::attr(" in selector_str:
        sel, rest = selector_str.split("::attr(", 1)
        attr = rest.rstrip(")")
        tag = item.select_one(sel.strip())
        if not tag:
            return ""
        value = tag.get(attr, "")
        # href 如果是相對路徑，補上 base domain
        if attr == "href" and value and not value.startswith("http"):
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            if value.startswith("/"):
                value = f"{parsed.scheme}://{parsed.netloc}{value}"
            else:
                value = f"{parsed.scheme}://{parsed.netloc}/{value}"
        return value or ""
    else:
        tag = item.select_one(selector_str.strip())
        return tag.get_text(strip=True) if tag else ""


def _parse_with_fields(
    soup: Any,
    source: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    使用 feeds.yml 的 selector + fields 配置解析。
    fields 支援 title / url / summary 三個欄位名稱。
    """
    selector = source.get("selector")
    if not selector:
        LOGGER.warning("%s 未設定 selector，跳過", source.get("name"))
        return []

    fields: Dict[str, str] = source.get("fields", {})
    limit = int(source.get("limit", 10))
    base_url = source.get("url", "")
    name = source.get("name", source.get("key", "unknown"))

    items = soup.select(selector)
    if not items:
        LOGGER.warning("%s 找不到條目（selector: %s）", name, selector)
        return []

    entries = []
    for item in items[:limit]:
        # title
        title = _resolve_field(item, fields.get("title"), base_url)
        if not title:
            continue

        # url → 對應 collector 的 link 欄位
        link = _resolve_field(item, fields.get("url"), base_url)

        # summary
        summary = _resolve_field(item, fields.get("summary"), base_url)

        entries.append({
            "title": title,
            "link": link,           # collector 的 build_payload 用 link
            "summary": summary,
            "published": "",        # web 來源通常無發布時間
            "source": source.get("name", "未知來源"),
            "source_key": source.get("key", "unknown"),
            "tags": source.get("tags", []),
            "category": source.get("category", "未分類"),
        })

    return entries


def fetch_web_source(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    抓取單一 type: web 來源。

    保護機制：
    - timeout 10 秒，不會無限等待
    - 最多重試 2 次
    - 任何錯誤只回傳空列表，不拋出 exception
    """
    name = source.get("name", source.get("key", "unknown"))
    url = source.get("url", "")

    if not url:
        LOGGER.warning("%s 未設定 url，跳過", name)
        return []

    LOGGER.info("抓取網頁來源：%s", name)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            entries = _parse_with_fields(soup, source)
            LOGGER.info("%s 成功取得 %d 筆資料", name, len(entries))
            return entries

        except requests.exceptions.Timeout:
            LOGGER.warning("%s Timeout（嘗試 %d/%d）", name, attempt, MAX_RETRIES)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        except requests.exceptions.HTTPError as exc:
            LOGGER.warning("%s HTTP 錯誤：%s（嘗試 %d/%d）", name, exc, attempt, MAX_RETRIES)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        except requests.exceptions.RequestException as exc:
            LOGGER.warning("%s 網路錯誤：%s（嘗試 %d/%d）", name, exc, attempt, MAX_RETRIES)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.error("%s 未預期錯誤：%s，跳過", name, exc)
            return []

    LOGGER.warning("%s 所有嘗試均失敗，跳過", name)
    return []


if __name__ == "__main__":
    # 本地測試：直接執行此檔案
    import yaml
    import pathlib

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    feeds_path = pathlib.Path("ops/feeds.yml")

    with feeds_path.open(encoding="utf-8") as f:
        config = yaml.safe_load(f)

    for src in config.get("sources", []):
        if src.get("type") == "web" and src.get("enabled", True):
            print(f"\n[Web] 抓取 {src['name']} ...")
            data = fetch_web_source(src)
            for d in data:
                print(f"  - {d['title']} | {d['link']}")
