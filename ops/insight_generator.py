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
然後掃描「今日最新 AI 情報列表」，挑選出最精華的 50 篇重點情報，並針對每一篇提出落地方案。**

分析輸出必須嚴格遵守以下格式（請列出 TOP 1 到 TOP 50）：

---
### 📍 TOP 1: [文章標題或工具名稱]
- **來源：** [來源]
- **命中缺口：** 對應你研究中的哪個 Phase / Layer / 問題編號（如 E01、H01...）
- **初步戰略提案：** 這項新技術相比現有選型多了什麼能力？建議在我們的研究中如何應用（請給出具體實驗或落地做法）？

### 📍 TOP 2... (以此類推，直到挑滿 50 篇，若不足 50 篇則有幾篇列幾篇)
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
    
    # 不設限，把當日所有收集到的百篇生肉全數投入初篩池（Gemini Flash 百萬 Token 足以吃下數百篇）
    top_entries = sorted_entries[:500]
    
    lines = []
    for i, e in enumerate(top_entries, 1):
        title = e.get('title', '(無標題)')
        source = e.get('source_key', '')
        
        full_summary = e.get('summary_raw', '')
        # 強制擷取至少 50% 的原文內文，最多不超過 2500 字，確保模型有深度的上下文判斷
        read_len = max(int(len(full_summary) * 0.5), min(len(full_summary), 2500))
        summary = full_summary[:read_len]
        
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
你的任務是無情檢視 AI 戰略軍師推薦的「Top 50 重點情報戰略」，逐篇（逐一）抓出它們無法在 Brownfield 老工廠落地的缺點。

你的考核基準（極限條件 Checklist）：
1. 邊緣算力限制：系統只能跑在 Jetson Orin Nano 8GB 上（大型 LLM / Transformer 難以負荷）。
2. 網路環境極限：工廠內部網路不穩，所有影響機台作動的推論必須離線。
3. 即時性要求：端到端延遲 (E2E Latency) 不能超過 2 秒。
4. 感測噪聲預期：金屬會反光、現場有油污粉塵，純 RGB 高精度依賴會失效。
5. 硬體改裝禁忌：不准改動機器原廠的安全迴路與硬體。

以下是軍師提出的 Top 50 初步戰略：
{initial_insight}

請針對這幾個提案「逐一篇章」給出評估。格式必須如下：

### 審查 TOP 1: [文章標題]
- **【判定結果】**: PASS 或 REJECT
- **【廠長嚴批】**: (詳細說明理由。若 REJECT 點出違反了哪一條限制；若 PASS 提醒落地注意事項)

### 審查 TOP 2... (依此類推，逐篇審查)
"""
        critic_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=critic_prompt
        )
        critic_feedback = critic_response.text
        LOGGER.info(f"魔鬼審查完成。")

        # --- Revision Phase ---
        if "REJECT" in critic_feedback.upper():
            LOGGER.info("有提案被退回，軍師正在進行逐篇自我修正 (Reflection)...")
            revise_prompt = f"""軍師，你先前的 Top 50 戰略提案已經被具有實務經驗的廠長（魔鬼審查員）逐篇審查並給予無情批評。
以下是廠長的逐篇審查意見：
{critic_feedback}

=== 你的原初稿內容 ===
{initial_insight}
=================

請根據廠長的批評，執行自我修正 (Self-Correction)，重新撰寫一份務實的「Top 精華情報大會審 (V2 妥協版)」。
對於被廠長 `REJECT` 的提案，你必須放棄原先誇大的想法，改為「降級妥協方案」（例如大模型改用知識蒸餾版、放在雲端離線處理、或是引入 Execution Gating 保守策略等），或者如果不具備任何落地可能，直接標註「因硬體限制擱置」。
對於被廠長 `PASS` 的提案，請保留並寫入廠長的警語。

請使用以下格式逐一列出這幾篇精華情報：
### 📍 TOP 1: [文章標題]
- **命中缺口：** ...
- **最終可落地方案 (經廠長審查)：** (結合你的原意與廠長的限制，給出最務實的做法)

### 📍 TOP 2... (依此類推，直到挑滿 50 篇)
"""
            revise_response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=revise_prompt
            )
            final_insight = revise_response.text
            debate_log = f"\n\n### ⚠️ 【幕後沙盤演練紀實：逐篇審查與修正】\n\n{critic_feedback}\n\n- **🔄 軍師自我修正**：已根據廠長意見，將不切實際的方案降級，產出上述 V2 策略。\n"
        else:
            final_insight = initial_insight
            debate_log = f"\n\n### ⚠️ 【幕後沙盤演練紀實：魔鬼審查全數通過】\n\n{critic_feedback}\n"
            
        insight_content = final_insight + debate_log

        LOGGER.info("最終洞察報告 (含逐篇沙盤辯論紀錄) 準備完成！")
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
