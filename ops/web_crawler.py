"""網頁爬蟲模組：抓取 type: web 來源，使用 scrapling 原生 API。"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

try:
    import requests
except ImportError as exc:
    raise SystemExit("請先安裝 requests：pip install requests") from exc

from scrapling.parser import Selector

try:
    from scrapling.fetchers import Fetcher, StealthyFetcher, DynamicFetcher  # type: ignore

    _SCRAPLING_FETCHERS_AVAILABLE = True
except Exception:
    _SCRAPLING_FETCHERS_AVAILABLE = False

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


# ---------------------------------------------------------------------------
# 共用欄位解析（使用 scrapling 原生 ::text / ::attr() 語法）
# ---------------------------------------------------------------------------

def _resolve_field(item: Any, selector_str: Optional[str], base_url: str = "") -> str:
    """
    解析單一欄位，支援多選擇器（逗號分隔），依序嘗試。

    scrapling 原生已支援：
      - "h2 a::text"         → 取文字
      - "h2 a::attr(href)"   → 取屬性
      - "h2 a"               → 取元素文字（預設加 ::text）
    """
    if not selector_str:
        return ""

    selectors = [s.strip() for s in selector_str.split(",") if s.strip()]
    for sel in selectors:
        if "::attr(" in sel:
            # 屬性選擇器：直接用 scrapling 原生
            result = item.css(sel).get()
            if not result:
                continue
            # 相對路徑補全
            if "href" in sel and result and not result.startswith(("http", "//")):
                if not base_url:
                    return ""
                result = urljoin(base_url, result)
            return result
        elif "::text" in sel:
            # 明確的文字選擇器
            result = item.css(sel).get()
            if result:
                return result.strip()
        else:
            # 預設取元素文字
            result = item.css(f"{sel}::text").get()
            if result:
                return result.strip()

    return ""


# ---------------------------------------------------------------------------
# HTML 解析（不觸網，純解析）
# ---------------------------------------------------------------------------

def _parse_with_fields(
    page: Any,
    source: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    使用 feeds.yml 的 selector + fields 配置解析頁面。
    page 可以是 scrapling Selector 物件或 fetcher 回傳的 page 物件。
    """
    selector = source.get("selector")
    if not selector:
        LOGGER.warning("%s 未設定 selector，跳過", source.get("name"))
        return []

    fields: Dict[str, str] = source.get("fields", {})
    limit = int(source.get("limit", 10))
    base_url = source.get("url", "")
    name = source.get("name", source.get("key", "unknown"))

    items = page.css(selector)
    if not items:
        body_text = page.css("body::text").get() or ""
        if len(body_text) < 200:
            LOGGER.warning(
                "%s 找不到條目（selector: %s），頁面內容過短，可能為 JS 渲染頁面或 selector 錯誤",
                name, selector,
            )
        else:
            LOGGER.warning("%s 找不到條目（selector: %s）", name, selector)
        return []

    entries: List[Dict[str, Any]] = []
    for item in items[:limit]:
        title = _resolve_field(item, fields.get("title"), base_url)
        if not title:
            continue
        link = _resolve_field(item, fields.get("url"), base_url)
        summary = _resolve_field(item, fields.get("summary"), base_url)

        entries.append({
            "title": title,
            "link": link,
            "summary": summary,
            "published": "",
            "source": source.get("name", "未知來源"),
            "source_key": source.get("key", "unknown"),
            "tags": source.get("tags", []),
            "category": source.get("category", "未分類"),
        })

    return entries


# ---------------------------------------------------------------------------
# 主要抓取函式
# ---------------------------------------------------------------------------

def fetch_web_source(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    抓取單一 type: web 來源。

    策略：
    1. 若 scrapling fetchers 可用且 source 有指定 fetcher → 用 scrapling fetcher
    2. 否則用 requests + Selector 解析

    保護機制：timeout 10 秒、最多重試 2 次、任何錯誤回傳空列表。
    """
    name = source.get("name", source.get("key", "unknown"))
    url = source.get("url", "")

    if not url:
        LOGGER.warning("%s 未設定 url，跳過", name)
        return []

    LOGGER.info("抓取網頁來源：%s", name)

    # ── 策略 1：scrapling fetcher（dynamic/stealthy/fetcher）────────────
    fetcher_type = source.get("fetcher")
    if _SCRAPLING_FETCHERS_AVAILABLE and fetcher_type in ("dynamic", "stealthy", "fetcher"):
        try:
            page = None
            if fetcher_type == "dynamic":
                page = DynamicFetcher.fetch(url, headless=True, network_idle=True)
            elif fetcher_type == "stealthy":
                page = StealthyFetcher.fetch(url, headless=True)
            else:
                page = Fetcher.get(url, stealthy_headers=True)

            entries = _parse_with_fields(page, source)
            LOGGER.info("%s (scrapling/%s) 成功取得 %d 筆資料", name, fetcher_type, len(entries))
            return entries
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.warning("%s scrapling 抓取失敗：%s，回退到 requests", name, exc)

    # ── 策略 2：requests + Selector（fallback）─────────────────────────
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if "application/json" in content_type or len(response.text) < 2000:
                LOGGER.warning(
                    "%s 取得的頁面可能為 JSON 或 JS 渲染，length=%d, content-type=%s",
                    name, len(response.text), content_type,
                )

            page = Selector(response.text)
            entries = _parse_with_fields(page, source)
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
