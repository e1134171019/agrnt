"""從 collector 產出的 JSON 生成 Markdown 摘要。"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import pathlib
import sys
import os
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
                # 显示后处理 LLM 输出（若存在）
                manuf_score = item.get("manufacturing_applicability_score")
                if manuf_score is not None:
                    lines.append(f"**Manufacturing applicability score**：{manuf_score}/100")
                note = item.get("sensor_cad_integration_note")
                if note:
                    lines.append(f"**Sensor/CAD integration note**：{note}")
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

    # 后处理：对 papers 类别使用 LLM/启发式提取 manufacturing applicability score 与 integration note
    try:
        from typing import cast

        def _postprocess_paper(entry: Dict[str, Any]) -> None:
            title = entry.get("title", "") or ""
            summary = entry.get("summary_raw", "") or ""
            text = f"{title}\n\n{summary}".lower()

            # 尝试使用 OpenAI（若环境变量和库存在），否则使用简单关键词启发式
            openai_key = os.environ.get("OPENAI_API_KEY")
            if openai_key:
                try:
                    import openai

                    openai.api_key = openai_key
                    prompt = (
                        f"请基于以下论文标题与摘要，给出一个 0-100 的 'manufacturing applicability' 分数，"
                        f"并在一到两句话中说明是否涉及传感器整合或 CAD/CAM 集成（返回纯文本）。\n\n{text}"
                    )
                    resp = openai.ChatCompletion.create(
                        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=200,
                        temperature=0.0,
                    )
                    content = resp["choices"][0]["message"]["content"].strip()
                    # 解析返回：尝试提取数字和文字备注
                    import re

                    m = re.search(r"(\d{1,3})", content)
                    score = int(m.group(1)) if m else None
                    note = content
                except Exception:
                    score = None
                    note = "(LLM 处理失败，使用启发式结果)"
            else:
                # 启发式规则：若包含 manufacturing/sensor/cad/cnc/robot keywords 则评分较高
                score = 10
                keywords = ["manufactur", "sensor", "cnd", "cnc", "robot", "assembly", "digital twin", "predictive maintenance", "cad", "cam"]
                hits = sum(1 for kw in keywords if kw in text)
                score = min(100, 20 + hits * 20)
                note = "; ".join([kw for kw in ["sensor integration likely" if "sensor" in text else "", "CAD/CAM relevance" if "cad" in text or "cam" in text else ""] if kw]) or "No clear sensor/CAD integration detected"

            if score is not None:
                entry["manufacturing_applicability_score"] = int(score)
            if note:
                entry["sensor_cad_integration_note"] = note

        for e in entries:
            if (e.get("category") or "").lower() == "papers":
                _postprocess_paper(e)
    except Exception:
        LOGGER.exception("论文后处理步骤发生异常，继续生成摘要")

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
