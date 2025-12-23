"""收集所有啟用的 feeds 並輸出標準化 JSON。"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import pathlib
import sys
import time
from typing import Any, Dict, List

try:
    import feedparser  # type: ignore
except ImportError as exc:
    raise SystemExit("請先安裝 feedparser：pip install feedparser") from exc

try:
    import requests
except ImportError as exc:
    raise SystemExit("請先安裝 requests：pip install requests") from exc

try:
    import yaml
except ImportError as exc:
    raise SystemExit("請先安裝 PyYAML：pip install pyyaml") from exc

ROOT = pathlib.Path(__file__).resolve().parents[1]
FEEDS_PATH = ROOT / "ops" / "feeds.yml"
OUT_DIR = ROOT / "out"
LOGS_DIR = ROOT / "logs"
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_ENTRIES_PER_SOURCE = 50
LOGGER = logging.getLogger("collector")


def setup_logging(verbose: bool = False, log_file: pathlib.Path | None = None) -> None:
    """Configure console/file logging similar to digest."""
    level = logging.DEBUG if verbose else logging.INFO
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")
    )

    handlers = [console_handler]
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            )
        )
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers)


def load_config(path: pathlib.Path) -> Dict[str, Any]:
    """Load feeds.yml and ensure mandatory fields are present."""
    if not path.exists():
        LOGGER.error(f"設定檔不存在：{path}")
        sys.exit(1)

    try:
        with path.open("r", encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        LOGGER.error(f"YAML 格式錯誤：{exc}")
        sys.exit(1)

    if not config or "sources" not in config:
        LOGGER.error("設定檔缺少 'sources' 欄位")
        sys.exit(1)

    seen_keys: set[str] = set()
    for idx, source in enumerate(config["sources"]):
        missing = [field for field in ("key", "name", "url", "type") if field not in source]
        if missing:
            LOGGER.error(f"來源 #{idx} 缺少必要欄位：{', '.join(missing)}")
            sys.exit(1)
        if source["type"] not in {"rss", "atom"}:
            LOGGER.error(f"來源 '{source['name']}' 的 type 必須是 'rss' 或 'atom'")
            sys.exit(1)
        if source["key"] in seen_keys:
            LOGGER.error(f"來源 key '{source['key']}' 重複")
            sys.exit(1)
        seen_keys.add(source["key"])

    LOGGER.info(f"載入設定：{path}")
    return config


def fetch_feed(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Fetch entries for a single source with retries."""
    name = source["name"]
    url = source["url"]
    LOGGER.info(f"抓取來源：{name}")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()

            feed = feedparser.parse(response.content)
            if feed.bozo:
                LOGGER.warning(f"{name} 解析時出現警告：{feed.bozo_exception}")

            entries: List[Dict[str, Any]] = []
            for entry in feed.entries[:MAX_ENTRIES_PER_SOURCE]:
                entries.append(
                    {
                        "title": entry.get("title", "無標題"),
                        "link": entry.get("link", ""),
                        "summary": entry.get("summary", entry.get("description", "")),
                        "published": entry.get("published", entry.get("updated", "")),
                        "source": name,
                        "source_key": source.get("key", "unknown"),
                        "tags": source.get("tags", []),
                    }
                )

            LOGGER.info(f"成功取得 {len(entries)} 筆資料")
            return entries
        except requests.Timeout:
            LOGGER.warning(f"{name} Timeout (嘗試 {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
        except requests.RequestException as exc:
            LOGGER.warning(f"{name} 網路錯誤：{exc} (嘗試 {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
        except Exception as exc:  # pylint: disable=broad-except
            LOGGER.error(f"{name} 未預期錯誤：{exc}")
            break

    LOGGER.warning(f"{name} 所有嘗試均失敗，跳過")
    return []


def merge_entries(all_entries: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Flatten and deduplicate entries by link."""
    flat = [entry for entries in all_entries for entry in entries]
    seen_links: set[str] = set()
    unique: List[Dict[str, Any]] = []

    for entry in flat:
        link = entry.get("link", "")
        if not link or link in seen_links:
            continue
        seen_links.add(link)
        unique.append(entry)

    LOGGER.info(f"合併後共 {len(unique)} 筆（去重前 {len(flat)} 筆）")
    return unique


def build_payload(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Attach metadata required by downstream digest."""
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    payload: List[Dict[str, Any]] = []

    for entry in entries:
        payload.append(
            {
                "source_key": entry.get("source_key", "unknown"),
                "source": entry.get("source", "未知來源"),
                "title": entry.get("title", "無標題"),
                "url": entry.get("link", ""),
                "summary_raw": entry.get("summary", ""),
                "tags": entry.get("tags", []),
                "fetched_at": fetched_at,
                "published_at": entry.get("published", ""),
            }
        )

    return payload


def write_payload(payload: List[Dict[str, Any]], path: pathlib.Path) -> None:
    """Persist payload as UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    LOGGER.info(f"產出原始資料：{path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="收集 feeds 並輸出 JSON")
    parser.add_argument(
        "--date",
        type=str,
        default=dt.date.today().isoformat(),
        help="指定日期 (YYYY-MM-DD)，用於輸出檔名",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="自訂輸出檔案（預設：out/raw-{date}.json）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="僅顯示統計資訊，不寫檔",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="顯示 DEBUG 級別日誌",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log_file = LOGS_DIR / f"collector-{args.date}.log" if not args.dry_run else None
    setup_logging(verbose=args.verbose, log_file=log_file)

    LOGGER.info("=" * 50)
    LOGGER.info("開始執行 collector")
    LOGGER.info(f"日期：{args.date}")
    LOGGER.info("=" * 50)

    config = load_config(FEEDS_PATH)
    sources = [s for s in config["sources"] if s.get("enabled", True)]
    if not sources:
        LOGGER.error("沒有啟用的資料來源")
        sys.exit(2)

    collected: List[List[Dict[str, Any]]] = []

    for source in sources:
        entries = fetch_feed(source)
        if entries:
            collected.append(entries)

    if not collected:
        LOGGER.error("所有來源都失敗")
        sys.exit(2)

    merged = merge_entries(collected)
    payload = build_payload(merged)

    if args.dry_run:
        LOGGER.info(f"Dry-run 模式，預計輸出 {len(payload)} 筆資料")
        LOGGER.debug(json.dumps(payload[:3], ensure_ascii=False, indent=2))
    else:
        output_path = args.output or OUT_DIR / f"raw-{args.date}.json"
        try:
            write_payload(payload, output_path)
        except OSError as exc:
            LOGGER.error(f"寫入檔案失敗：{exc}")
            sys.exit(3)

    LOGGER.info("collector 執行完成")


if __name__ == "__main__":
    main()
