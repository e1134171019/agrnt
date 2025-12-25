"""從 collector 產出的 JSON 生成 Markdown 摘要。"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import pathlib
import sys
from typing import Any, Dict, List, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "out"
LOGS_DIR = ROOT / "logs"
RAW_PREFIX = "raw"
LOGGER = logging.getLogger("digest")


def setup_logging(verbose: bool = False, log_file: pathlib.Path | None = None) -> None:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="讀取 JSON 並產出 Markdown 摘要")
    parser.add_argument(
        "--date",
        type=str,
        default=dt.date.today().isoformat(),
        help="指定日期 (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--input",
        type=pathlib.Path,
        help="自訂 JSON 輸入路徑（預設：out/raw-{date}.json）",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="自訂輸出 Markdown（預設：out/digest-{date}.md）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="僅顯示結果不寫檔",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="顯示 DEBUG 級別日誌",
    )
    return parser.parse_args()


def load_entries(path: pathlib.Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not path.exists():
        LOGGER.error(f"找不到 JSON 檔案：{path}")
        sys.exit(1)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        LOGGER.error(f"JSON 解析失敗：{exc}")
        sys.exit(1)

    if isinstance(data, dict):
        entries = data.get("entries")
        if entries is None:
            LOGGER.error("JSON 缺少 'entries' 欄位")
            sys.exit(1)
        meta = data.get("meta", {})
    elif isinstance(data, list):
        entries = data
        meta = {}
    else:
        LOGGER.error("JSON 格式錯誤，預期為列表或包含 entries 的物件")
        sys.exit(1)

    if not isinstance(entries, list):
        LOGGER.error("'entries' 欄位格式錯誤，預期為列表")
        sys.exit(1)

    required = {"source", "title", "url", "summary_raw", "published_at", "category"}
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            LOGGER.error(f"第 {idx} 筆資料格式錯誤（預期為物件）")
            sys.exit(1)
        missing = required - entry.keys()
        if missing:
            LOGGER.error(f"第 {idx} 筆資料缺少欄位：{', '.join(sorted(missing))}")
            sys.exit(1)

    return entries, meta


def generate_markdown(
    entries: List[Dict[str, Any]],
    date: str,
    meta: Dict[str, Any] | None = None,
) -> str:
    lines = [f"# 技術資訊摘要 - {date}", ""]

    if meta:
        lines.append("## 摘要指標")
        lines.append("")
        raw_entries = meta.get("raw_entries")
        unique_entries = meta.get("unique_entries", len(entries))
        dedup_rate = meta.get("dedup_rate")
        if raw_entries is not None or dedup_rate is not None:
            dedup_text = (
                f"{float(dedup_rate) * 100:.2f}%"
                if isinstance(dedup_rate, (int, float))
                else "N/A"
            )
            if raw_entries is not None:
                lines.append(
                    f"- 去重率：{dedup_text}（原始 {raw_entries} → 去重 {unique_entries}）"
                )
            else:
                lines.append(f"- 去重率：{dedup_text}")

        category_counts = meta.get("category_counts") or {}
        if isinstance(category_counts, dict) and category_counts:
            parts = [f"{cat} {count} 筆" for cat, count in sorted(category_counts.items())]
            lines.append(f"- 分類統計：{' / '.join(parts)}")

        total_sources = meta.get("total_sources")
        failed_count = meta.get("failed_source_count")
        if isinstance(total_sources, int) and isinstance(failed_count, int):
            success = total_sources - failed_count
            lines.append(
                f"- 來源健康度：成功 {success} / {total_sources}（失敗 {failed_count}）"
            )

        failed_sources = meta.get("failed_sources") or []
        if isinstance(failed_sources, list) and failed_sources:
            failed_names = [
                item.get("name") or item.get("key", "未知來源")
                for item in failed_sources
                if isinstance(item, dict)
            ]
            if failed_names:
                lines.append(f"- 失敗來源：{', '.join(failed_names)}")

        lines.append("")

    by_category: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for entry in entries:
        category = entry.get("category", "未分類") or "未分類"
        source = entry.get("source", "未知來源")
        by_category.setdefault(category, {}).setdefault(source, []).append(entry)

    for category in sorted(by_category):
        lines.append(f"## {category}")
        lines.append("")
        sources = by_category[category]
        for source in sorted(sources):
            lines.append(f"### {source}")
            lines.append("")
            for item in sources[source]:
                title = item.get("title", "無標題")
                url = item.get("url", "")
                summary_full = item.get("summary_raw", "")
                summary = summary_full[:200]
                published = item.get("published_at", "未知時間")
                tags = " ".join(f"#{tag}" for tag in item.get("tags", []))

                lines.append(f"#### [{title}]({url})" if url else f"#### {title}")
                lines.append(f"發布於：{published}")
                lines.append("")
                if summary:
                    suffix = "..." if len(summary_full) > 200 else ""
                    lines.append(summary + suffix)
                    lines.append("")
                lines.append(f"**來源**：{source}")
                if tags:
                    lines.append(f"**標籤**：{tags}")
                lines.append("")
                lines.append("---")
                lines.append("")

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"*本摘要由自動化系統產生於 {now}*")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    log_file = LOGS_DIR / f"digest-{args.date}.log"
    setup_logging(verbose=args.verbose, log_file=log_file)

    LOGGER.info("=" * 50)
    LOGGER.info("開始產出 digest")
    LOGGER.info(f"日期：{args.date}")
    LOGGER.info("=" * 50)

    input_path = args.input or OUT_DIR / f"{RAW_PREFIX}-{args.date}.json"
    entries, meta = load_entries(input_path)
    if not entries:
        LOGGER.error("JSON 沒有資料，無法產出摘要")
        sys.exit(2)

    markdown = generate_markdown(entries, args.date, meta)

    if args.dry_run:
        LOGGER.info("Dry-run 模式，輸出預覽在 stdout")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(markdown)
    else:
        output_path = args.output or OUT_DIR / f"digest-{args.date}.md"
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown, encoding="utf-8")
            LOGGER.info(f"產出摘要：{output_path}")
        except OSError as exc:
            LOGGER.error(f"寫入檔案失敗：{exc}")
            sys.exit(3)

    LOGGER.info("digest 執行完成")


if __name__ == "__main__":
    main()
