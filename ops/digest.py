"""根據 feeds.yml 抓取最新資訊並輸出 Markdown Digest。

使用方式：
    python ops/digest.py                     # 產生今天的摘要
    python ops/digest.py --date 2025-12-20  # 產生指定日期
    python ops/digest.py --dry-run          # 預覽模式
    python ops/digest.py --verbose          # 詳細日誌
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import pathlib
import sys
from typing import Any, Dict, List

try:
    import feedparser
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

# 常數定義
ROOT = pathlib.Path(__file__).resolve().parents[1]
FEEDS_PATH = ROOT / "ops" / "feeds.yml"
OUT_DIR = ROOT / "out"
LOGS_DIR = ROOT / "logs"
REQUEST_TIMEOUT = 30  # 秒
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒

LOGGER = logging.getLogger("digest")


def setup_logging(verbose: bool = False, log_file: pathlib.Path | None = None) -> None:
    """設定日誌輸出。"""
    level = logging.DEBUG if verbose else logging.INFO
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S"
    """載入並驗證 feeds.yml 設定檔。"""
    if not path.exists():
        LOGGER.error(f"設定檔不存在：{path}")
        sys.exit(1)
    
    try:
        with path.open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        LOGGER.error(f"YAML 格式錯誤：{e}")
        sys.exit(1)
    
    if not config or "sources" not in config:
        LOGGER.error("設定檔缺少 'sources' 欄位")
        sys.exit(1)
    
    # 驗證每個來源
    for idx, source in enumerate(config["sources"]):
        if not all(k in source for k in ["name", "url", "type"]):
            LOGGER.error(f"來源 #{idx} 缺少必要欄位 (name/url/type)")
            sys.exit(1)
        if source["type"] not in ["rss", "atom"]:
            LOGGER.error(f"來源 '{source['name']}' 的 type 必須是 'rss' 或 'atom'")
            sys.exit(1)
    
    LOGGER.info(f"載入設定：{path}")
    returnfeed(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    """抓取並解析單一 RSS/Atom feed。"""
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
            
            entries = []
            for entry in feed.entries[:50]:  # 最多 50 筆
                entries.append({
                    "title": entry.get("title", "無標題"),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", entry.get("description", "")),
                    "published": entry.get("published", entry.get("updated", "")),
                    "source": name,
                    "tags": source.get("tags", []),
                })
            
            LOGGER.info(f"成功取得 {len(entries)} 筆資料")
            return entries
        
        except requests.Timeout:
            LOGGER.warning(f"{name} Timeout (嘗試 {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                import time
                time.sleep(RETRY_DELAY)
        except requests.RequestException as e:
            LOGGER.warning(f"{name} 網路錯誤：{e} (嘗試 {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES:
                import time
                time.sleep(RETRY_DELAY)
        except Exception as e:
            LOGGER.error(f"{name} 未預期錯誤：{e}")
            break
    
    LOGGER.warning(f"{name} 所有嘗試均失敗，跳過")
    return []


def merge_entries(all_entries: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """合併所有來源並去重。"""
    flat = [entry for entries in all_entries for entry in entries]
    
    # 去重（依 link）
    seen = set()
    unique = []
    for entry in flat:
        link = entry.get("link", "")
        if link and link not in seen:
            seen.add(link)
            unique.append(entry)
    
    LOGGER.info(f"合併後共 {len(unique)} 筆（去重前 {len(flat)} 筆）")
    return unique


def generate_markdown(entries: List[Dict[str, Any]], date: str) -> str:
    """產生 Markdown 格式摘要。"""
    lines = [
        f"# 技術資訊摘要 - {date}",
        "",
    ]
    
    # 按來源分組
    by_source: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        source = entry.get("source", "未知來源")
        by_source.setdefault(source, []).append(entry)
    
    for source, items in sorted(by_source.items()):
        lines.append(f"## {source}")
        lines.append("")
        
        for item in items:
            title = item.get("title", "無標題")
            link = item.get("link", "")
            summary = item.get("summary", "")[:200]  # 限制長度
            published = item.get("published", "未知時間")
            tags = " ".join(f"#{tag}" for tag in item.get("tags", []))
            
            lines.append(f"### [{title}]({link})")
            lines.append(f"發布於：{published}")
            lines.append("")
            if summary:
                lines.append(summary + "...")
                lines.append("")
            lines.append(f"**來源**：{source}")
            if tags:
                lines.append(f"**標籤**：{tags}")
            lines.append("")
            lines.append("---")
            lines.append("")
    
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"*本摘要由自動化系統產生於 {now}*")
    
    return "\n".join(linesfeed.get("id", "未命名來源"))
        body.append(f"## {title}")
        body.append(f"- 類型：{feed.get('type', 'n/a')} | 更新頻率：{feed.get('cadence', 'n/a')}")
        body.append(f"- 來源連結：{feed.get('url', 'N/A')}")
        if not items:
            body.append("- 無可用項目，請稍後再試。")
            body.append("")
            continue
        for idx, item in enumerate(items, start=1):
            title_line = f"{idx}. {item.get('title', '未命名項目')}"
            if item.get("url"):
                title_line += f" — {item['url']}"
            extras = []
            if item.get("score") is not None:
                extras.append(f"指標 {item['score']}")
            if item.get("author"):
                extras.append(f"作者 {item['author']}")
            if extras:
                title_line += f" ({', '.join(extras)})"
            body.append(title_line)
            if item.get("description"):
                body.append(f"   - 摘要：{item['description']}")
        body.append("")
    return "\n".join(header + body)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="抓取 feeds.yml 並生成每日情資摘要")
    parser.add_argument("--date", help="指定日期 (YYYY-MM-DD)")
    parser.add_argument("--output", help="輸出檔案路徑，預設印出到終端", default="")
    parser.add_argument("--dry-run", action="store_true", help="使用內建假資料，避免實際呼叫 API")
    parser.add_argument("--verbose", action="store_true", help="輸出除錯資訊")
    return parser.parse_args()


def build_fake_results() -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    dummy_feed = {"title": "範例來源", "type": "demo", "cadence": "daily", "url": "https://example.com"}
    dummy_items = [
        {
    """解析命令列參數。"""
    parser = argparse.ArgumentParser(description="產生技術資訊摘要")
    parser.add_argument(
        "--date",
        type=str,
        default=dt.date.today().isoformat(),
        help="指定日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="輸出檔案路徑（預設：out/digest-{date}.md）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="僅顯示預覽，不寫入檔案",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="詳細日誌輸出",
    )
    return parser.parse_args()


def main() -> None:
    """主程式。"""
    args = parse_args()
    
    # 設定日誌
    log_file = LOGS_DIR / f"digest-{args.date}.log" if not args.dry_run else None
    setup_logging(verbose=args.verbose, log_file=log_file)
    
    LOGGER.info("=" * 50)
    LOGGER.info("開始執行 digest")
    LOGGER.info(f"日期：{args.date}")
    LOGGER.info("=" * 50)
    
    # 載入設定
    config = load_config(FEEDS_PATH)
    sources = [s for s in config["sources"] if s.get("enabled", True)]
    
    if not sources:
        LOGGER.error("沒有啟用的資料來源")
        sys.exit(2)
    
    # 抓取所有來源
    all_entries = []
    for source in sources:
        entries = fetch_feed(source)
        if entries:
            all_entries.append(entries)
    
    if not all_entries:
        LOGGER.error("所有來源都失敗")
        sys.exit(2)
    
    # 合併並產生 Markdown
    merged = merge_entries(all_entries)
    markdown = generate_markdown(merged, args.date)
    
    # 輸出
    if args.dry_run:
        print("\n" + "=" * 50)
        print("預覽模式（不寫入檔案）")
        print("=" * 50 + "\n")
        print(markdown)
    else:
        output_path = args.output or OUT_DIR / f"digest-{args.date}.md"
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown, encoding="utf-8")
            LOGGER.info(f"產生摘要：{output_path}")
        except OSError as e:
            LOGGER.error(f"寫入檔案失敗：{e}")
            sys.exit(3)
    
    LOGGER.info("執行完成"