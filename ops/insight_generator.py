import argparse
import datetime as dt
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any

from google import genai

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
OUT_DIR = PROJECT_ROOT / "out"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)

SYSTEM_PROMPT = """
你是一位工業 5.0 與邊緣 AI 的頂級首席技術長兼戰略幕僚。
你的老闆正在研究一個「中小企業折床機台 AI 化 MVP 系統」。
他目前硬體採用：奧比中光 Gemini 336Lg (工業級 RGB-D 深度相機帶 GMSL 無延遲傳輸) + Jetson邊緣運算。
他正在比較兩種系統架構的效益：
1. 主流大廠方案：多視角機台感測 (IP Camera/336GL) + 事件化觸發異常 + MQTT 雲端下放 控制。
2. 創新破局方案：第一視角 (AR 眼鏡) 捕捉人類老師傅不可言傳的操作經驗 (6D 姿態、視線)。

老闆的四大核心研究痛點是：
P1: 狀態不可觀測 (OC - Unobservable State)
P2: 錯誤不可即時阻止 (Latent Error)
P3: 經驗無法累積與學習 (Experience Not Learning)
P4: 圖檔設計與現場製造的意圖斷層 (Intent Parsing / Unstructured Intent)

請閱讀以下由爬蟲今天最新整理出來的研究與開源情報。
請寫下一篇約 300~500 字的「高管深度戰略分析報告」，重點在於：
1. 從中挑選最亮眼或最具啟發性的 2-3 篇論文或開源工具 (標註其名稱)。
2. 解釋這幾個新技術如何直接應用於老闆的 336GL 多視角系統，或者如何強化 AR 眼鏡的「經驗採集」能力。
3. 給出一個直接的行動建議 (例如：用 A 技術解決 P2 延遲問題，用 B 理論解決 P4 意圖流失)。

寫作風格：專業、犀利、直接切入重點，語氣像是一位頂尖幕僚。
"""

def generate_insights(date_str: str) -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        LOGGER.error("未找到 GEMINI_API_KEY 環境變數，跳過生成洞察報告")
        return

    raw_json_path = OUT_DIR / f"raw-{date_str}.json"
    if not raw_json_path.exists():
        LOGGER.error(f"找不到原始資料檔 {raw_json_path}")
        return

    with open(raw_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = data.get("entries", [])
    if not entries:
        LOGGER.warning("今日無任何情報，跳過生成")
        return

    # 排序：有分數優先，無分數者其次
    def get_score(e):
        s = e.get("manufacturing_applicability_score", 0)
        return float(s) if str(s).replace('.', '', 1).isdigit() else 0.0

    sorted_entries = sorted(entries, key=get_score, reverse=True)
    
    # 節錄前 50 篇（避免過度超出 context，但 Gemini 1.5 Flash 1M token 其實可以放更多）
    # 這裡我們擷取前 100 篇來保持精華並避免不必要的 token 消耗
    top_entries = sorted_entries[:100]
    
    context_lines = []
    for i, e in enumerate(top_entries, 1):
        title = e.get('title', '')
        source = e.get('source_key', '')
        summary = e.get('summary_raw', '')[:500] # 每篇摘要擷取 500 字元即足夠辨識意圖
        context_lines.append(f"[{i}] {title} (來源: {source})\n摘要: {summary}\n")

    context_text = "\n".join(context_lines)

    LOGGER.info("正在呼叫 Gemini API 產生深度洞察報告...")
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"{SYSTEM_PROMPT}\n\n【今日最新情報列表】\n{context_text}"
        )
        insight_content = response.text
        LOGGER.info("洞察報告生成成功！")
    except Exception as exc:
        LOGGER.exception(f"呼叫 Gemini API 失敗: {exc}")
        return

    # 將報告 prepend 到 main issue markdown 中
    main_md_path = OUT_DIR / f"digest-{date_str}-main.md"
    if main_md_path.exists():
        original_md = main_md_path.read_text(encoding='utf-8')
        
        # 組合新內容
        insight_header = "## 💡 AI 幕僚戰略洞察報告 (專注折床 MVP 效益)\n\n"
        insight_footer = "\n\n---\n\n"
        
        # 插入在標題和摘要指標之間
        lines = original_md.split('\n')
        target_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("## 摘要指標"):
                target_idx = i
                break
                
        new_md = "\n".join(lines[:target_idx]) + "\n" + insight_header + insight_content + insight_footer + "\n".join(lines[target_idx:])
        main_md_path.write_text(new_md, encoding='utf-8')
        LOGGER.info(f"已將洞察報告寫入 {main_md_path}")
    else:
        LOGGER.warning(f"找不到 {main_md_path}，無法插入洞察報告")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=dt.datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    generate_insights(args.date)
