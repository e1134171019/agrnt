import argparse
import datetime as dt
import json
import logging
import os
from pathlib import Path
from typing import Optional

from google import genai

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
OUT_DIR = PROJECT_ROOT / "out"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)

# 客觀新聞摘要 Prompt（無主觀研究偏見）
NEWS_SUMMARY_PROMPT = """
你是一位工業 AI 與科技領域的資深主編。
你的任務是閱讀以下「今日最新科技與製造業情報列表」，總結出最重要的新聞，寫成一份易讀的「世界科技晨報」。

請按照以下四大板塊分類輸出，每個板塊挑選出 1~3 條最重要的動態，用一句話總結其內容（請附上來源括號）。
如果該板塊今天沒有任何相關情報，請直接寫「今日無重大更新」。

---

### 🌍 世界科技晨報

#### 🤖 1. 頂級 AI 模型動態
> （例如：OpenAI, HuggingFace, Llama 等大模型的發布或重大更新）

#### 🏭 2. 商業製造與軟體設備
> （例如：Amada, Trumpf, SolidWorks, Autodesk 等商業巨頭的新聞，或工業互聯網平台動態）

#### 🔬 3. 學術前沿：視覺與機器人
> （例如：arXiv 上的 SLAM, 3DGS, 機器人 VLA, 電腦視覺新突破）

#### 📰 4. 其他值得關注的科技新聞
> （不在上述分類中，但影響深遠的開源專案、硬體發布或業界討論）

---

寫作要求：
- 務必保持客觀，不要加上對某個特定研究計畫的建議。
- 只選最重要的，不要流水帳把所有條目列出。
- 語氣簡明俐落，如報紙頭條版面般易讀。
"""

def load_today_news(date_str: str) -> str:
    """載入今日情報（從 raw JSON 讀取）"""
    raw_json_path = OUT_DIR / f"raw-{date_str}.json"
    if not raw_json_path.exists():
        LOGGER.error(f"找不到原始資料檔 {raw_json_path}")
        return ""

    with open(raw_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    entries = data.get("entries", [])
    if not entries:
        return ""

    # 用所有條目，不論分數（新聞可能分數低，但具廣泛價值）
    lines = []
    for i, e in enumerate(entries, 1):
        title = e.get('title', '(無標題)')
        source = e.get('source_key', '')
        summary = e.get('summary_raw', '')[:400]
        
        lines.append(f"[{i}] {title} ({source})\n   摘要: {summary}")
        
        # 限制讀取總數以免過載 (Gemini Flash Token 很夠，這裡取前 150 篇)
        if i >= 150:
            break
            
    return "\n\n".join(lines)


def generate_news_summary(date_str: str) -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        LOGGER.error("未找到 GEMINI_API_KEY 環境變數，跳過生成晨報")
        return

    # 載入今日情報
    LOGGER.info("載入今日情報用於晨報總結...")
    today_news = load_today_news(date_str)
    if not today_news:
        LOGGER.warning("今日無任何情報，跳過生成晨報")
        return

    # 組合 Prompt
    full_prompt = f"""{NEWS_SUMMARY_PROMPT}

---

# 以下是今日情報列表

{today_news}
"""

    LOGGER.info("正在呼叫 Gemini API 生成晨報...")
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_prompt
        )
        news_content = response.text
        LOGGER.info("晨報生成成功！")
    except Exception as exc:
        LOGGER.exception(f"呼叫 Gemini API 失敗: {exc}")
        return

    # 將晨報插入 main issue markdown 的最頂部
    main_md_path = OUT_DIR / f"digest-{date_str}-main.md"
    if main_md_path.exists():
        original_md = main_md_path.read_text(encoding='utf-8')
        
        news_block = (
            f"{news_content}\n\n"
            "---\n\n"
        )
        
        # 插入在最前面（"## 摘要指標" 或原來 "## 💡 AI 研究情報戰略分析" 的前面）
        lines = original_md.split('\n')
        insert_idx = 0
        for i, line in enumerate(lines):
            # 如果發現 insight_generator 先跑出來的區塊，就插它前面
            if line.startswith("## 💡 AI 研究情報戰略分析"):
                insert_idx = i
                break
            # 否則插在指標前面
            elif line.startswith("## 摘要指標") or line.startswith("## 📊"):
                insert_idx = i
                break
                
        if insert_idx > 0:
            new_lines = lines[:insert_idx] + [news_block] + lines[insert_idx:]
        else:
            new_lines = lines[:2] + [news_block] + lines[2:]
        
        main_md_path.write_text('\n'.join(new_lines), encoding='utf-8')
        LOGGER.info(f"已將科技晨報寫入 {main_md_path}")
    else:
        # 若 main 不存在，寫入獨立檔案
        news_only_path = OUT_DIR / f"news-{date_str}.md"
        news_only_path.write_text(news_content, encoding='utf-8')
        LOGGER.info(f"Main Digest 不存在，晨報已另存至 {news_only_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=dt.datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    generate_news_summary(args.date)
