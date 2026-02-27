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

# 研究文件定義（唯一 context：我的規劃.md 已整合問題空間 + 技術選型 + 文獻對應 + RBv3架構）
RESEARCH_DOCS = {
    "研究規劃說明書（P1-P4 × 130個問題 × 技術選型 × RBv3架構 × 優先缺口）": PROJECT_ROOT / "我的規劃.md",
}

# 分析框架 Prompt（缺口清單從研究文件動態讀取，不在此寫死）
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

> 請依據研究文件「4.3 核心解法架構」中列出的「尚未解決的關鍵缺口」，
> 逐一檢查今日情報是否有新的彌補：
> - 對有命中的項目：說明新技術如何處理
> - 對無命中的項目：標示「今日無新突破」

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
        # 唯一 context 文件，給足夠空間（25,000 字元）
        if len(content) > 25000:
            content = content[:25000] + "\n\n...(文件過長，已截取前段)\n"
        
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
        # 讀取新版 postprocessor 輸出的研究問題命中備註（相容舊欄位名）
        note = e.get("research_problem_note", "") or e.get("sensor_cad_integration_note", "")
        
        score_str = f" [研究相關度:{score:.0f}分]" if score > 0 else ""
        note_str = f"\n   > P1-P4命中: {note}" if note and "未命中" not in note and "No clear" not in note else ""
        
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
        initial_insight = response.text
        LOGGER.info("初稿戰略報告生成成功！正在進入魔鬼審查員 (Critic) 沙盤辯論...")

        # --- Critic Phase ---
        critic_prompt = f"""你是一位老派的工廠廠長兼工業 5.0 架構師（魔鬼審查員）。
你的任務是無情檢視這份 AI 戰略軍師推薦的學術戰略，把它不切實際、無法在 Brownfield 老工廠落地的缺點抓出來。

你的考核基準（極限條件 Checklist）：
1. 邊緣算力限制：系統只能跑在 Jetson Orin Nano 8GB 上（大型 LLM / Transformer 難以負荷）。
2. 網路環境極限：工廠內部網路不穩，所有影響機台作動的推論必須離線。
3. 即時性要求：端到端延遲 (E2E Latency) 不能超過 2 秒。
4. 感測噪聲預期：金屬會反光、現場有油污粉塵，純 RGB 高精度依賴會失效。
5. 硬體改裝禁忌：不准改動機器原廠的安全迴路與硬體。

以下是軍師提出的初步戰略：
{initial_insight}

請給出評估，必須遵守以下格式：
【判定結果】: PASS 或 REJECT
【魔鬼審查意見】: (詳細說明理由。若 REJECT 點出違反了哪一條限制；若 PASS 提醒落地注意事項)
"""
        critic_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=critic_prompt
        )
        critic_feedback = critic_response.text
        LOGGER.info(f"魔鬼審查完成。")

        # --- Revision Phase ---
        if "REJECT" in critic_feedback.upper():
            LOGGER.info("初稿被退回，軍師正在進行自我修正 (Reflection)...")
            revise_prompt = f"""你先前的戰略提案被具有實務經驗的廠長（魔鬼審查員）判定為不符合工廠現實而退回。
以下是廠長的審查意見：
{critic_feedback}

=== 原初稿內容 ===
{initial_insight}
=================

請根據廠長的批評，執行自我修正 (Self-Correction)，重新撰寫一份務實的「V2 妥協版」戰略分析。
同樣保持原有的三大段落結構（命中缺口、是否解決、行動建議），但行動建議必須改為「可落地方案」（如：大模型降級為 3B 模型、採用深度補全、引入 Execution Gating 保守策略等）。
"""
            revise_response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=revise_prompt
            )
            final_insight = revise_response.text
            debate_log = f"\n\n### ⚠️ 【幕後沙盤演練紀實：Reflection 自我修正】\n\n- **💥 魔鬼審查委員（廠長）退件理由**：\n{critic_feedback}\n- **🔄 軍師自我修正**：已放棄原先不切實際的方案，更新為上述更務實的 V2 策略。\n"
        else:
            final_insight = initial_insight
            debate_log = f"\n\n### ⚠️ 【幕後沙盤演練紀實：魔鬼審查通過】\n\n- **🛡️ 廠長審查意見**：\n{critic_feedback}\n"
            
        insight_content = final_insight + debate_log

        LOGGER.info("最終洞察報告 (含沙盤辯論紀錄) 準備完成！")
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
