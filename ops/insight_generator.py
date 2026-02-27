import argparse
import datetime as dt
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from google import genai

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
OUT_DIR = PROJECT_ROOT / "out"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)

# 研究文件定義（使用者的核心知識庫）
RESEARCH_DOCS = {
    "研究規劃（6M1E × 130個問題 × P1-P4）": PROJECT_ROOT / "我的規劃.md",
    "系統技術說明書（RBv3 × 三源共識 × 降級矩陣 × 硬體選型）": PROJECT_ROOT / "論文.md",
    "MVP 階段技術路線圖（Phase-0 到 Phase-5）": PROJECT_ROOT / "mvp-Phase.md",
    "67篇文獻摘要索引": PROJECT_ROOT / "文獻.md",
}

# 分析框架 Prompt（不寫死任何硬體或架構，由研究文件本身提供上下文）
ANALYSIS_FRAMEWORK = """
你是一位工業 5.0 × 中小企業製造 AI 的頂級首席技術長兼戰略幕僚。

你的任務是：
**閱讀「研究者的核心文件」，理解其正在驗證的方法論與技術架構，
然後掃描「今日最新 AI 情報列表」，找出可以直接填補研究缺口或強化現有方案的技術。**

分析輸出必須回答三個問題（按此結構分段輸出）：

---

### 📍 今日情報命中研究缺口

> 每個命中點格式：
> **[文章標題或工具名稱]**（來源）
> 命中位置：對應你研究中的哪個 Phase / Layer / 問題編號（如 E01、H01、B06...）
> 強化方式：這項新技術/工具，相比研究中現有選型，具體多了哪個能力或修正了哪個限制？

（至少找出 2 個命中點，若無則明確說明今日空白）

---

### 🧩 研究缺口是否仍存在

> 根據你理解的研究架構，以下幾個高優先缺口今日是否有新的彌補：
> - **E01 金屬反光深度失效**（視覺感知層核心難題）
> - **B06 冷啟動零資料**（Brownfield 最大挑戰）
> - **P4 DXF 意圖到現場的數位橋樑**（Layer 0 核心問題）
> - **P3 師傅經驗數位化**（持續學習 / 少量樣本學習）
>
> 對有命中的項目：說明新技術如何處理；對無命中的項目：標示「今日無新突破」

---

### 🎯 行動建議（直接可執行）

> 根據今日情報，給出 1 個最優先的具體行動建議。格式：
> 「建議在 【Phase X / Layer Y】 考慮採用 【工具或論文名稱】，
> 理由是它解決了現有方案中 【哪個具體技術限制】，
> 下一步可以 【做什麼實驗或初步測試】。」

---

寫作風格：直接、犀利、必須基於研究文件的具體內容（引用問題編號/Phase/Layer）。
禁止：空泛的「AI將改變製造業」等與研究無關的廢話。
"""


def load_research_context() -> str:
    """動態載入所有研究文件作為分析 Context"""
    context_parts = []
    
    for doc_name, doc_path in RESEARCH_DOCS.items():
        if not doc_path.exists():
            LOGGER.warning(f"找不到研究文件: {doc_path}")
            continue
        
        content = doc_path.read_text(encoding='utf-8')
        # 限制每份文件最多 15,000 字元，避免超過 context window
        if len(content) > 15000:
            content = content[:15000] + "\n\n...(文件過長，已截取前段)\n"
        
        context_parts.append(f"## {doc_name}\n\n{content}")
        LOGGER.info(f"載入研究文件: {doc_name} ({len(content)} 字元)")
    
    if not context_parts:
        LOGGER.error("沒有找到任何研究文件！")
        return ""
    
    return "\n\n---\n\n".join(context_parts)


def load_today_intel(date_str: str) -> str:
    """載入今日情報（從 raw JSON 讀取，優先取高分論文與社群討論）"""
    raw_json_path = OUT_DIR / f"raw-{date_str}.json"
    if not raw_json_path.exists():
        LOGGER.error(f"找不到原始資料檔 {raw_json_path}")
        return ""

    with open(raw_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = data.get("entries", [])
    if not entries:
        return ""

    # 排序：有 LLM 分數的優先，分數高的在前
    def get_score(e):
        s = e.get("manufacturing_applicability_score", 0)
        try:
            return float(s)
        except (TypeError, ValueError):
            return 0.0

    sorted_entries = sorted(entries, key=get_score, reverse=True)
    
    # 取前 80 篇（Gemini 1.5/2.0 Flash 有 1M Token，足以容納）
    top_entries = sorted_entries[:80]
    
    lines = []
    for i, e in enumerate(top_entries, 1):
        title = e.get('title', '(無標題)')
        source = e.get('source_key', '')
        summary = e.get('summary_raw', '')[:400]
        score = get_score(e)
        note = e.get("sensor_cad_integration_note", "")
        
        score_str = f" [製造相關度:{score:.0f}分]" if score > 0 else ""
        note_str = f"\n   > LLM備註: {note}" if note and "No clear" not in note else ""
        
        lines.append(f"[{i}] {title} ({source}){score_str}\n   摘要: {summary}{note_str}")
    
    return "\n\n".join(lines)


def generate_insights(date_str: str) -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        LOGGER.error("未找到 GEMINI_API_KEY 環境變數，跳過生成洞察報告")
        return

    # 載入研究文件
    LOGGER.info("載入研究核心文件...")
    research_context = load_research_context()
    if not research_context:
        LOGGER.error("無法載入研究文件，跳過分析")
        return

    # 載入今日情報
    LOGGER.info("載入今日情報...")
    today_intel = load_today_intel(date_str)
    if not today_intel:
        LOGGER.warning("今日無任何情報，跳過生成")
        return

    # 組合最終 Prompt
    full_prompt = f"""{ANALYSIS_FRAMEWORK}

---

# 以下是研究者的核心文件（你的分析基準）

{research_context}

---

# 以下是今日最新 AI / 製造技術情報列表（請掃描並對照研究文件分析）

{today_intel}
"""

    LOGGER.info(f"Prompt 總長度: {len(full_prompt)} 字元，正在呼叫 Gemini API...")
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_prompt
        )
        insight_content = response.text
        LOGGER.info("洞察報告生成成功！")
    except Exception as exc:
        LOGGER.exception(f"呼叫 Gemini API 失敗: {exc}")
        return

    # 將報告插入 main issue markdown 的最頂部
    main_md_path = OUT_DIR / f"digest-{date_str}-main.md"
    if main_md_path.exists():
        original_md = main_md_path.read_text(encoding='utf-8')
        
        insight_block = (
            "## 💡 AI 研究情報戰略分析\n"
            f"> 基於研究架構（事件化證據鏈 × 6M1E × P1-P4）× 今日 {date_str} 最新情報\n\n"
            + insight_content
            + "\n\n---\n\n"
        )
        
        # 找到「## 摘要指標」的位置，插入在它之前
        lines = original_md.split('\n')
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("## 摘要指標") or line.startswith("## 📊"):
                insert_idx = i
                break
        
        if insert_idx > 0:
            new_lines = lines[:insert_idx] + [insight_block] + lines[insert_idx:]
        else:
            # 若找不到插入點，加在開頭後面
            new_lines = lines[:2] + [insight_block] + lines[2:]
        
        main_md_path.write_text('\n'.join(new_lines), encoding='utf-8')
        LOGGER.info(f"已將研究洞察報告寫入 {main_md_path}")
    else:
        # 若 main 不存在，寫入獨立檔案
        insight_only_path = OUT_DIR / f"insights-{date_str}.md"
        insight_only_path.write_text(insight_content, encoding='utf-8')
        LOGGER.info(f"Main Digest 不存在，洞察報告已另存至 {insight_only_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=dt.datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    generate_insights(args.date)
