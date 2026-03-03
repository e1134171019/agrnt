"""
analyze_gaps.py
────────────────────────────────────────────────────────────────────────────────
用本機 67 篇文獻（文獻.md）對 Phase-1 技術待決清單（T01-T17）做一次全量比對。

輸出：out/gap_analysis_<date>.md
────────────────────────────────────────────────────────────────────────────────
"""

import datetime
import logging
import os
from pathlib import Path

from google import genai

PROJECT_ROOT = Path(__file__).parent
OUT_DIR = PROJECT_ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ── T01-T17 待決清單（固定，不從文件動態讀取，避免 prompt 過度膨脹）──────────
PENDING_LIST = """
| 編號 | 層面 | 待決問題 |
|------|-----|---------|
| T01 | 感知層 | 金屬鏡面 E01：Jetson 8GB 上哪個深度補全實作能在 ≤2秒內完成？需要的演算法和模型？ |
| T02 | 感知層 | 3DGS 建圖方案：哪個實作？每次換線需要重建嗎？Jetson 上渲染速度多少？ |
| T03 | 感知層 | 多相機 Rig 標定：換線後是否需要重標定？W-Shift 最大能補正多大的偏差？ |
| T04 | 事件層 | BBB PRU 邊沿時戳精度：理論 <10ns，實際 jitter 多少？對 ±300ms 對齊夠嗎？ |
| T05 | 事件層 | plc.edge → Jetson 傳輸協議：UDP vs MQTT，在封閉工廠 LAN 端到端延遲多少？ |
| T06 | 推理層 | Jetson 8GB 全管線延遲：3DGS渲染 + 深度比對 + 三源投票，實際能跑幾 ms？ |
| T07 | 推理層 | 步驟辨識模型選型：ProgressLM-3B / LLaVA-7B / 其他？幾 bit 量化才能在 Jetson 跑？ |
| T08 | DXF層 | P4 主線路線：A（DXF解析工序）/ B（補生成DXF）/ C（VLM直接理解 CAD）？哪個最可行？ |
| T09 | DXF層 | file_pfid 算法設計：對哪些折線幾何特徵做 hash？不同 CAD 軟體輸出 DXF 格式一致嗎？ |
| T10 | 持續學習 | 持續學習觸發時機：每班結束？每週 batch？累積 N 個異常事件才更新？ |
| T11 | 持續學習 | Jetson 8GB 記憶體預算：骨幹模型佔多少 GB？EWC/replay buffer 還剩多少空間？ |
| T12 | 冷啟動 | Unity 合成資料 domain gap：sim-to-real 遷移需要多少真實圖才能 fine-tune 到可用？ |
| T13 | 冷啟動 | 最小標注集：不依賴 Unity，直接在真實折床，最少標注幾張/幾折才能從零啟動？ |
| T14 | 系統整合 | RBv3 存儲格式：SQLite vs InfluxDB vs 純 JSON？單日 100 折的儲存空間是多少？ |
| T15 | 系統整合 | A/B 對照實驗設計：如何定義有無提示的邊界？需要多少折彎樣本才達到統計顯著？ |
| T16 | 驗收門檻 | E2E latency 驗收標準：P50 和 P95 各要達到多少才算 Phase-1 通過？ |
| T17 | 驗收門檻 | 可追溯覆蓋率 Coverage 下限：≥ 多少才能宣告 Phase-1 成立？如何定義必要欄位集 F_req？ |
"""

PROMPT_TEMPLATE = """你是一位研究方法論專家，正在協助一位研究者規劃「中小企業板金折床工站智慧化系統（Phase-1）」的論文。

研究者有 17 個具體的「技術設計待決問題（T01-T17）」。
他已經評析了 67 篇相關論文，儲存在下方的文獻庫中。

## 你的任務
對每一個 T 編號（T01-T17），從 67 篇文獻中找出哪些文章能直接或間接幫助回答它。
輸出一份「文獻比對報告」，告訴研究者：哪幾個 T 可以「現在就填答案」，哪幾個必須找新論文。

---

## Phase-1 技術待決清單（T01-T17）

{PENDING_LIST}

---

## 已評析的 67 篇文獻全文

{LITERATURE}

---

## 輸出格式規範

輸出分為三個區塊，請嚴格按照以下格式：

---

# 📊 67 篇文獻 × T01-T17 技術待決比對報告

> 分析日期：{DATE}
> 文獻庫規模：67 篇（3.1-3.12 章節）

---

## 🟢 可立即填寫（文獻庫已有充分依據）

> 這些 T 項目，現有 67 篇中已有足夠資訊可以做出技術選型決策。

對每個「可填寫」的 T 項目，輸出以下格式：

### ✅ [T編號] [待決問題一行摘要]

**建議填入的答案：**
[具體的技術選型或設計決策，2-5 句話，要有數值或明確結論]

**主要依據文獻：**
- [[編號]] [論文名稱]：[一句話說明這篇如何回答這個待決問題]
- [[編號]] [論文名稱]：[一句話說明]

**信心度：** 高 / 中
**理由：** [為什麼這個答案可信，有沒有什麼前提條件]

---

## 🟡 部分澄清（文獻有線索，但不足以完全確定）

> 這些 T 項目，現有文獻提供了重要線索，但還需要一篇關鍵缺失論文或實際實測才能確定。

對每個「部分澄清」的 T 項目：

### ⚡ [T編號] [待決問題一行摘要]

**現有文獻提供的線索：**
- [[編號]]：[提供什麼線索]

**還缺什麼：**
[一到兩句話，需要哪類論文或哪種實驗才能完全回答]

**缺口嚴重性：** 高 / 中 / 低（說明對 Phase-1 啟動的影響）

---

## 🔴 文獻庫無法回答（需要主動尋找新論文）

> 這些 T 項目，現有 67 篇幾乎沒有相關文獻，必須主動搜尋。

對每個「無法回答」的 T 項目：

### ❌ [T編號] [待決問題一行摘要]

**缺失的論文類型：**
[描述需要找什麼樣的論文：關鍵詞、研究方向、推薦哪幾個會議或期刊]

**建議 arXiv 搜尋關鍵詞：**
`[keyword1] [keyword2] [keyword3]`

---

## 📋 T01-T17 完整狀態總表

| 編號 | 待決問題（簡） | 狀態 | 主要依據文獻 | 行動建議 |
|------|--------------|------|------------|---------|
| T01 | ... | 🟢可填/🟡部分/🔴缺失 | [文獻編號] | ... |
| T02 | ... | ... | ... | ... |
（T03 到 T17 以此類推，共 17 行）

---

## 💡 優先行動建議（Top 3）

[告訴研究者，為了讓 Phase-1 最快啟動，現在最緊迫的三個行動是什麼]

1. **立即可做：** [利用🟢項目可以做的事]
2. **本週補足：** [找哪些關鍵論文來解決🟡項目]
3. **必須確認：** [哪個項目如果不解決，Phase-1 無法啟動]
"""


def load_literature() -> str:
    path = PROJECT_ROOT / "文獻.md"
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}")
    text = path.read_text(encoding="utf-8")
    log.info(f"載入文獻.md：{len(text)} 字元")
    return text


def load_planning() -> str:
    path = PROJECT_ROOT / "我的規劃.md"
    if not path.exists():
        raise FileNotFoundError(f"找不到 {path}")
    text = path.read_text(encoding="utf-8")
    log.info(f"載入我的規劃.md：{len(text)} 字元")
    return text


def run():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("未找到 GEMINI_API_KEY 環境變數")

    literature = load_literature()
    date_str = datetime.date.today().isoformat()

    prompt = PROMPT_TEMPLATE.format(
        PENDING_LIST=PENDING_LIST,
        LITERATURE=literature,
        DATE=date_str,
    )

    log.info(f"Prompt 總長度：{len(prompt)} 字元，正在呼叫 Gemini 2.5 Pro...")

    client = genai.Client(api_key=api_key)
    # 使用 gemini-2.5-flash（已驗證可用，1M context window 足夠裝下 67 篇文獻）
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    result = response.text
    log.info(f"Gemini 回應長度：{len(result)} 字元")

    out_path = OUT_DIR / f"gap_analysis_{date_str}.md"
    out_path.write_text(result, encoding="utf-8")
    log.info(f"✅ 報告已寫入：{out_path}")
    print(f"\n{'='*60}")
    print(f"完成！請開啟：{out_path}")
    print(f"{'='*60}\n")
    print(result[:3000])   # 印出前 3000 字預覽


if __name__ == "__main__":
    run()
