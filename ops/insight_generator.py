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

# 研究文件定義（三份文件：規劃地圖 + 工程規格 + 已評析文獻索引）
# Gemini 2.5 Flash context window = 1,000,000 tokens，三份合計 ~60,000 字，完全不需要截斷規劃文件
RESEARCH_DOCS = {
    "研究規劃說明書（P1-P4 × 130個問題 × 技術選型 × RBv3架構 × 優先缺口）": PROJECT_ROOT / "我的規劃.md",
    "工程規格書（RBv3架構 × 硬體BOM × 量化指標 × §4.3四個開放缺口）": PROJECT_ROOT / "論文.md",
    "已評析文獻索引（67篇 × 防止重複推薦 × P1-P4對應）": PROJECT_ROOT / "文獻.md",
}

# 各文件截斷上限（字元）。文獻.md 只需章節索引，取前段即可；其他完整載入
DOC_TRUNCATE = {
    "我的規劃.md": 40000,
    "論文.md":    30000,
    "文獻.md":    15000,  # 前 15000 字已含全部文獻索引與章節標題
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
    """動態載入所有研究文件作為分析 Context（三份文件：規劃 + 工程規格 + 已評析文獻）"""
    context_parts = []

    for doc_name, doc_path in RESEARCH_DOCS.items():
        if not doc_path.exists():
            LOGGER.warning(f"找不到研究文件: {doc_path}")
            continue

        content = doc_path.read_text(encoding='utf-8')
        limit = DOC_TRUNCATE.get(doc_path.name, 40000)
        if len(content) > limit:
            content = content[:limit] + f"\n\n...(已截取前 {limit} 字元)\n"

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

    # 過濾：過濾掉分數 < 30 且未命中 P1-P4 痛點的垃圾情報
    filtered_entries = []
    for e in entries:
        score = get_score(e)
        note = e.get("research_problem_note", "") or e.get("sensor_cad_integration_note", "")
        
        # 保留分數 >= 30，或是明確命中痛點的文章
        if score >= 30 or (note and "未命中" not in note and "No clear" not in note):
            filtered_entries.append(e)

    # 防空保護：如果過濾後為空（可能是評分未執行），改用全部 entries 不過濾
    if not filtered_entries:
        LOGGER.warning("過濾後無任何情報（可能是評分未執行），改用全部 entries")
        filtered_entries = entries

    sorted_entries = sorted(filtered_entries, key=get_score, reverse=True)
    
    # 取過濾後的所有高分生肉（Gemini Flash 容許額度內）
    top_entries = sorted_entries[:500]
    
    lines = []
    for i, e in enumerate(top_entries, 1):
        title = e.get('title', '(無標題)')
        source = e.get('source_key', '')
        
        full_summary = e.get('summary_raw', '')
        # 強制擷取至少 50% 的原文內文，但上限 2500 字（避免單篇極長文章超量）
        read_len = min(max(int(len(full_summary) * 0.5), 200), 2500)
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

        # --- 廠長 A：研究廠長（事前地圖完善，才能審出有意義的研究方向）---
        critic_a_prompt = f"""你是一位熟讀研究計畫的「研究廠長」。
你的任務只有一件事：**判斷軍師提出的每篇提案，對這個研究的「知識地圖建構」有沒有價值**。

⚠️ 這個階段你不管技術能不能跑、有沒有開源碼。那是下一位廠長的事。
你只管：「這篇論文或工具，有沒有填補我們研究地圖上的空格？」

你手上有完整的研究文件（含 §4.3 四個開放缺口、67 篇已評析文獻清單、B01-B15 Brownfield 約束）。

判定結果只有四種：
- **SIGNAL**    ：直接命中 P1/P2/P3/P4 或四個開放缺口（E01/B06/P4語意/P3災難遺忘），有明確的研究方向填補價值。
- **WATCH**     ：技術方向間接相關，不是核心缺口但值得持續追蹤。
- **DUPLICATE** ：已評析文獻索引中有相同技術（必須引用具體的文獻編號，如「已在 [32] DKT 評析」）。
- **NOISE**     ：與本研究 P1-P4 及 6M1E 無任何關聯。

以下是軍師提出的 Top 50 初步戰略：
{initial_insight}

請逐篇評估，格式如下：

### 研究審查 TOP 1: [文章標題]
- **【研究判定】**: SIGNAL / WATCH / DUPLICATE / NOISE
- **【理由】**: (SIGNAL 請引用具體問題編號或缺口；DUPLICATE 請引用文獻編號；NOISE 一句話說明為何無關)
"""
        critic_a_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=critic_a_prompt
        )
        critic_a_feedback = critic_a_response.text
        LOGGER.info("研究廠長 A 審查完成。")

        # --- 廠長 B：部署廠長（只審 SIGNAL 那幾篇）---
        critic_b_prompt = f"""你是一位深諳工廠實務的「部署廠長」兼工業 5.0 架構師。
研究廠長已經篩出「有研究方向價值」的提案（SIGNAL），你現在只需要審查這些 SIGNAL 提案的落地可行性。

你的三把刀：
1. 🔪 開源可用性：有無 GitHub/HuggingFace 程式碼/權重？
   - 有碼 → 進入下一把刀
   - 無碼但方向明確 → **PENDING CODE**（列入待追蹤，等碼釋出）
2. 🔪 硬體可跑性：
   - Jetson Orin Nano 8GB 邊緣推論可行 → **PASS**
   - 只能後台 RTX 5070 Ti 離線處理 → **PASS（限後台）**
   - 連後台都跑不動（A100 only，無蒸餾路徑） → **PENDING CODE**（等量化/蒸餾版本）
3. 🔪 Brownfield 抗性：
   - 違反 B06（需大量標注）、B11（需穩定網路）、B08（金屬反光直接失效）者，降級為 **PASS（限後台）** 或說明規避方案。

以下是研究廠長的審查結果（請找出 SIGNAL 的條目逐一審查）：
{critic_a_feedback}

請只針對 SIGNAL 條目逐篇評估，格式如下：

### 部署審查 TOP X: [文章標題]
- **【部署判定】**: PASS / PASS（限後台）/ PENDING CODE
- **【廠長說明】**: (引用具體 B 編號或硬體規格；PENDING CODE 請說明「等什麼才能用」)
"""
        critic_b_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=critic_b_prompt
        )
        critic_b_feedback = critic_b_response.text
        LOGGER.info("部署廠長 B 審查完成。")

        # --- Revision Phase：軍師整合兩位廠長意見 ---
        LOGGER.info("軍師正在整合兩位廠長意見，產出最終報告...")
        revise_prompt = f"""軍師，你的 Top 50 提案已經過兩位廠長審查：

【研究廠長 A 的意見】（判斷研究地圖價值）：
{critic_a_feedback}

【部署廠長 B 的意見】（判斷落地可行性，只審 SIGNAL）：
{critic_b_feedback}

=== 你的原初稿內容 ===
{initial_insight}
=================

請根據兩位廠長的意見，整合產出最終版「研究情報彙整報告 V2」，規則如下：

- **SIGNAL + PASS / PASS（限後台）**：完整保留，附部署廠長警語。這是「可立即行動」的情報。
- **SIGNAL + PENDING CODE**：保留研究方向說明，標記「⏳ 待碼追蹤：[說明等待什麼]」。這是「列入觀察名單」的情報。
- **WATCH**：以一句話保留，標記「👀 持續關注」。不需展開。
- **DUPLICATE**：標記「📚 已收錄於文獻.md [編號]，本次新增補充：[說明本次情報比已評析版本多了什麼新資訊]」。
- **NOISE**：直接移除，不出現在最終報告。

請按以下格式輸出：

## 🎯 可立即行動（SIGNAL + PASS）
### 📍 [文章標題]
- **命中缺口：** ...
- **落地方案：** ...
- **廠長警語：** ...

## ⏳ 待碼追蹤（SIGNAL + PENDING CODE）
### 📍 [文章標題]
- **命中缺口：** ...
- **研究方向價值：** ...
- **待追蹤：** 等 [什麼條件] 釋出後即可行動

## 👀 持續關注（WATCH）
- [文章標題]：[一句話說明關注原因]

## 📚 已收錄文獻補充（DUPLICATE）
- [文章標題]：已在文獻.md [編號] 評析。本次補充：[新資訊]
"""
        revise_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=revise_prompt
        )
        final_insight = revise_response.text
        LOGGER.info("整合報告完成。正在進行 Phase-5：規劃更新建議（T01-T17 待決清單比對）...")

        # --- Phase 5：規劃更新廠長（對照 T01-T17 技術待決清單）---
        planning_update_prompt = f"""你是研究計畫的「規劃更新廠長」。

你的任務：閱讀今天的 SIGNAL 論文，對照「Phase-1 技術待決清單（T01-T17）」，
判斷今天有哪些新論文**可以幫助填寫某個待決項目**。

## 技術待決清單（T01-T17）：

| 編號 | 待決問題 |
|------|---------|
| T01 | 金屬鏡面 E01：Jetson 8GB 上能否在 ≤2秒內完成深度補全？需要哪個實作？ |
| T02 | 3DGS 建圖方案：哪個實作？每次換線需要重建嗎？建圖時間？ |
| T03 | 多相機 Rig 標定：換線後是否需要重標？W-Shift 能補多大偏差？ |
| T04 | BBB PRU 邊沿時戳精度：jitter 實測值是多少？±300ms 對齊夠嗎？ |
| T05 | plc.edge → Jetson 傳輸協議：UDP vs MQTT，端到端延遲多少？ |
| T06 | Jetson 8GB 三源共識全管線延遲：3DGS 渲染 + 比對 + 投票實際多少 ms？ |
| T07 | 步驟辨識模型選型：ProgressLM-3B / LLaVA-7B / 其他？幾 bit 量化？ |
| T08 | P4 主線路線：A（DXF解析工序）/ B（補生成DXF）/ C（VLM直接理解）？ |
| T09 | file_pfid 算法：對哪些幾何特徵 hash？不同 CAD 軟體 DXF 格式一致嗎？ |
| T10 | 持續學習觸發時機：每班結束？每週？累積 N 個異常事件？ |
| T11 | Jetson 8GB 持續學習記憶體預算：骨幹多少 GB？replay buffer 多少？ |
| T12 | Unity 合成資料 domain gap：需要多少真實圖才能 fine-tune 到可用？ |
| T13 | 最小標注集：不依賴 Unity，最少標注幾張圖才能冷啟動？ |
| T14 | RBv3 存儲格式：SQLite vs InfluxDB vs JSON？單日 100 折 = 多少 GB？ |
| T15 | A/B 對照實驗：如何定義邊界？需要多少折彎樣本才達統計顯著？ |
| T16 | E2E latency：P50 和 P95 各要達到多少才算 Phase-1 合格？ |
| T17 | 可追溯覆蓋率 Coverage ≥ 多少才能說 Phase-1 成立？ |

## 今日 SIGNAL 論文（可立即行動 + 待碼追蹤）：
{final_insight}

## 你的任務：

對每篇 SIGNAL 論文，判斷它是否能幫助回答上面任何一個 T 編號的待決問題。

**輸出格式：**

## 📋 規劃待決更新建議

### 🟢 可填寫（今天的論文直接回答了待決問題）
- **[T編號] [待決問題簡述]**
  - 依據論文：[論文標題]
  - 建議填入：[具體的技術選型建議或數值，一到三句話]
  - 信心度：高 / 中 / 低（說明為何）

### 🟡 部分澄清（今天的論文提供了線索，但還不夠確定）
- **[T編號] [待決問題簡述]**
  - 依據論文：[論文標題]
  - 澄清了什麼：[一句話]
  - 還需要什麼才能完全確定：[一句話]

### 🔴 今日無相關（沒有新論文能幫助任何待決項目）
（如果所有 SIGNAL 論文都無法回答任何 T 編號，直接寫此標題後說明原因）

注意：請只輸出這個格式的規劃更新建議區塊，不要重複整份情報報告。
"""
        planning_update_response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=planning_update_prompt
        )
        planning_update = planning_update_response.text
        LOGGER.info("規劃更新建議（T01-T17 比對）完成。")

        debate_log = (
            f"\n\n---\n\n"
            f"### 🔬 【研究廠長 A 審查紀錄】\n\n{critic_a_feedback}\n\n"
            f"### 🏭 【部署廠長 B 審查紀錄】\n\n{critic_b_feedback}\n"
        )
            
        insight_content = final_insight + "\n\n---\n\n" + planning_update + debate_log

        LOGGER.info("最終洞察報告（廠長A + 廠長B + 規劃更新建議）準備完成！")
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
